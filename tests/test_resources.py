"""Verify Tier-A candidate resource discovery and region boundaries."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cyber_oedo.analysis.build_resource_map import OUTPUT_FIELDS, main
from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.resources import (
    ResourceHeader,
    build_candidate_regions,
    discover_resource_headers,
    read_sector_header_name,
)


def synthetic_payload(
    sectors: int,
    headers: dict[int, str],
) -> bytes:
    """Build a sector-aligned payload containing selected ASCII headers."""

    if sectors <= 0:
        raise ValueError("sectors must be positive")
    payload = bytearray(sectors * SECTOR_SIZE)
    for sector, name in headers.items():
        if not 0 <= sector < sectors:
            raise ValueError("header sector lies outside synthetic payload")
        encoded = name.encode("ascii")
        start = sector * SECTOR_SIZE
        payload[start:start + len(encoded)] = encoded
    return bytes(payload)


class ResourceHeaderTests(unittest.TestCase):
    """Exercise direct sector-boundary resource-name discovery."""

    def test_non_text_resource_keeps_neighboring_boundaries_narrow(self) -> None:
        """Keep MARKETT between KURUZER and MAYA01 in the region map."""

        payload = synthetic_payload(
            760,
            {
                747: "KURUZER",
                751: "MARKETT",
                755: "MAYA01",
            },
        )
        headers = discover_resource_headers(payload)
        selected = tuple(
            header
            for header in headers
            if 747 <= header.sector <= 755
        )
        self.assertEqual(
            selected,
            (
                ResourceHeader(747, "KURUZER"),
                ResourceHeader(751, "MARKETT"),
                ResourceHeader(755, "MAYA01"),
            ),
        )
        regions = build_candidate_regions(selected, 760)
        self.assertEqual(regions[0].sector_count, 4)
        self.assertEqual(regions[0].end_sector, 751)
        self.assertEqual(regions[1].sector_count, 4)
        self.assertEqual(regions[2].end_sector, 760)
        self.assertEqual(regions[2].boundary_source, "track_end")

    def test_short_candidate_name_is_not_lost_to_four_byte_scan_limit(self) -> None:
        """Recognize a valid short header directly from the sector start."""

        payload = synthetic_payload(2, {1: "AF"})
        self.assertEqual(read_sector_header_name(payload, 1), "AF")

    def test_repeated_fill_like_identifier_is_rejected(self) -> None:
        """Reject uniform uppercase fill that resembles an ASCII name."""

        payload = synthetic_payload(1, {0: "UUUUUUUU"})
        self.assertIsNone(read_sector_header_name(payload, 0))

    def test_overlong_identifier_is_not_truncated_into_false_header(self) -> None:
        """Reject a name continuing beyond the 16-byte identifier limit."""

        payload = synthetic_payload(1, {0: "ABCDEFGHIJKLMNOPQ"})
        self.assertIsNone(read_sector_header_name(payload, 0))

    def test_unaligned_payload_is_rejected(self) -> None:
        """Require exact sector geometry before scanning resource headers."""

        with self.assertRaises(ValueError):
            discover_resource_headers(b"not-sector-aligned")

    def test_duplicate_header_sectors_are_rejected(self) -> None:
        """Refuse ambiguous candidate regions with duplicate sector starts."""

        headers = (
            ResourceHeader(1, "FIRST"),
            ResourceHeader(1, "SECOND"),
        )
        with self.assertRaises(ValueError):
            build_candidate_regions(headers, 3)

    def test_header_outside_track_is_rejected(self) -> None:
        """Refuse candidate headers that lie beyond the payload."""

        with self.assertRaises(ValueError):
            build_candidate_regions((ResourceHeader(3, "LATE"),), 3)


class ResourceMapCommandTests(unittest.TestCase):
    """Verify the complete candidate resource-map TSV command."""

    def test_command_emits_every_header_and_marks_ownership_unproven(self) -> None:
        """Write textless candidate resources instead of filtering by dialogue."""

        payload = synthetic_payload(
            8,
            {
                1: "KURUZER",
                3: "MARKETT",
                6: "MAYA01",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            track = root / "track.bin"
            output = root / "resources.tsv"
            track.write_bytes(payload)
            status = main([str(track), str(output)])
            with output.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as source:
                rows = list(csv.DictReader(source, delimiter="\t"))
        self.assertEqual(status, 0)
        self.assertEqual(tuple(rows[0]), OUTPUT_FIELDS)
        self.assertEqual(
            [row["resource_name"] for row in rows],
            ["KURUZER", "MARKETT", "MAYA01"],
        )
        self.assertEqual(rows[0]["sector_count"], "2")
        self.assertEqual(rows[1]["sector_count"], "3")
        self.assertEqual(rows[2]["sector_count"], "2")
        self.assertTrue(
            all(row["ownership_status"] == "unproven" for row in rows)
        )


if __name__ == "__main__":
    unittest.main()
