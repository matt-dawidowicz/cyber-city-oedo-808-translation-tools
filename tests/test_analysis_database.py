"""Verify the generated Tier-A SQLite evidence database."""

from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cyber_oedo.analysis.build_analysis_db import main as build_database
from cyber_oedo.analysis.build_resource_map import main as build_resource_map
from cyber_oedo.contracts import DIALOGUE_V1, TRANSLATION_INVENTORY_V1
from cyber_oedo.disc.game_layout import SECTOR_SIZE


def write_tsv(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    """Write a small UTF-8 TSV fixture with an explicit ordered header."""

    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=fields,
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_payload() -> bytes:
    """Return a four-sector payload with two candidate resource headers."""

    payload = bytearray(4 * SECTOR_SIZE)
    payload[SECTOR_SIZE:SECTOR_SIZE + 7] = b"KURUZER"
    start = 3 * SECTOR_SIZE
    payload[start:start + 6] = b"MAYA01"
    return bytes(payload)


class AnalysisDatabaseTests(unittest.TestCase):
    """Exercise database ingestion, identity, ranges, and cleanup behavior."""

    def test_database_joins_translation_offsets_to_candidate_resources(
        self,
    ) -> None:
        """Query one occurrence against the resource interval containing it."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            track = root / "track.bin"
            resource_map = root / "resources.tsv"
            dialogue = root / "dialogue.tsv"
            inventory = root / "inventory.tsv"
            database = root / "analysis.sqlite"
            track.write_bytes(build_payload())
            build_resource_map([str(track), str(resource_map)])

            offset = SECTOR_SIZE + 100
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [
                    {
                        "bank": "MISSION_0",
                        "quality": "likely_text",
                        "offset": f"0x{offset:08X}",
                        "sector": 1,
                        "within_sector": "0x064",
                        "record_bytes": 12,
                        "sjis_characters": 4,
                        "controls": "40",
                        "tagged_text": "猫<$40>犬",
                        "text": "猫犬",
                        "raw_hex": "27 28 00",
                    }
                ],
            )
            write_tsv(
                inventory,
                TRANSLATION_INVENTORY_V1.fields,
                [
                    {
                        "entry_id": "E00001",
                        "canonical_id": "T00001",
                        "occurrence_count": 1,
                        "kind": "dialogue",
                        "bank": "MISSION_0",
                        "quality": "likely_text",
                        "offset": f"0x{offset:08X}",
                        "sector": 1,
                        "source_bytes": 12,
                        "controls": "40",
                        "source_text": "猫犬",
                        "tagged_source": "猫<$40>犬",
                        "english_translation": "Cat. Dog.",
                        "translator_notes": "synthetic",
                    }
                ],
            )

            status = build_database(
                [
                    str(database),
                    "--resource-map",
                    str(resource_map),
                    "--dialogue",
                    str(dialogue),
                    "--inventory",
                    str(inventory),
                ]
            )
            self.assertEqual(status, 0)
            connection = sqlite3.connect(database)
            try:
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "resource_candidates",
                        "dialogue_records",
                        "translation_occurrences",
                    )
                }
                resource = connection.execute(
                    """
                    SELECT r.resource_name
                    FROM translation_occurrences AS t
                    JOIN resource_candidates AS r
                      ON t.offset >= r.resource_offset
                     AND t.offset < r.end_offset_exclusive
                    WHERE t.entry_id = ?
                    """,
                    ("E00001",),
                ).fetchone()
                metadata = dict(
                    connection.execute(
                        "SELECT key, value FROM metadata"
                    )
                )
            finally:
                connection.close()

        self.assertEqual(counts["resource_candidates"], 2)
        self.assertEqual(counts["dialogue_records"], 1)
        self.assertEqual(counts["translation_occurrences"], 1)
        self.assertEqual(resource, ("KURUZER",))
        self.assertEqual(metadata["schema_version"], "1")
        self.assertEqual(len(metadata["resource_map_sha256"]), 64)
        self.assertEqual(len(metadata["dialogue_sha256"]), 64)
        self.assertEqual(
            len(metadata["translation_inventory_sha256"]),
            64,
        )

    def test_existing_database_requires_explicit_overwrite(self) -> None:
        """Refuse to replace generated evidence without an explicit flag."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "analysis.sqlite"
            resource_map = root / "resources.tsv"
            database.write_bytes(b"keep-me")
            write_tsv(
                resource_map,
                (
                    "resource_sector",
                    "resource_offset",
                    "resource_name",
                    "end_sector_exclusive",
                    "end_offset_exclusive",
                    "sector_count",
                    "byte_count",
                    "bank",
                    "boundary_source",
                    "ownership_status",
                ),
                [],
            )
            with self.assertRaises(SystemExit):
                build_database(
                    [
                        str(database),
                        "--resource-map",
                        str(resource_map),
                    ]
                )
            self.assertEqual(database.read_bytes(), b"keep-me")

    def test_ingest_failure_removes_partial_database(self) -> None:
        """Delete a partially initialized database when input validation fails."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "analysis.sqlite"
            invalid = root / "invalid.tsv"
            invalid.write_text("wrong\theader\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                build_database(
                    [
                        str(database),
                        "--dialogue",
                        str(invalid),
                    ]
                )
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
