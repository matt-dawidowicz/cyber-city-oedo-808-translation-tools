from __future__ import annotations

import unittest

from cyber_oedo.disc.resource_linker import (
    SECTOR_BYTES,
    ResourceObject,
    ResourceLinkError,
    build_resource_blob,
    descriptor_fields,
    link_resources,
)


class ResourceLinkerTests(unittest.TestCase):
    def test_resource_growth_moves_following_resource(self) -> None:
        resources = (
            ResourceObject("KURUZER", b"A" * 5000, original_sector=100, original_span=2),
            ResourceObject("MAYA01", b"B" * 1000, original_sector=102, original_span=1),
        )
        linked = link_resources(resources, start_sector=100)
        self.assertEqual(linked[0].start_sector, 100)
        self.assertEqual(linked[0].sector_span, 3)
        self.assertTrue(linked[0].grew)
        self.assertEqual(linked[1].start_sector, 103)
        self.assertTrue(linked[1].moved)

    def test_duplicate_names_fail_closed(self) -> None:
        with self.assertRaisesRegex(ResourceLinkError, "duplicate resource name"):
            link_resources((ResourceObject("A", b"a"), ResourceObject("A", b"b")), start_sector=1)

    def test_out_of_range_descriptor_rejected(self) -> None:
        row = link_resources((ResourceObject("A", b"a"),), start_sector=0x10000)[0]
        with self.assertRaisesRegex(ResourceLinkError, "sector exceeds"):
            descriptor_fields(row)

    def test_descriptor_tail_encodes_new_geometry(self) -> None:
        row = link_resources((ResourceObject("TEST", b"x" * 3000),), start_sector=0x1234)[0]
        self.assertEqual(descriptor_fields(row), bytes.fromhex("34 12 02 B8 0B 00"))

    def test_alignment_is_sector_based(self) -> None:
        rows = link_resources(
            (
                ResourceObject("A", b"a"),
                ResourceObject("B", b"b", alignment_sectors=4),
            ),
            start_sector=5,
        )
        self.assertEqual(rows[0].start_sector, 5)
        self.assertEqual(rows[1].start_sector, 8)

    def test_blob_places_resource_bytes_at_linked_sector_offsets(self) -> None:
        rows = link_resources(
            (ResourceObject("A", b"abc"), ResourceObject("B", b"xyz")),
            start_sector=10,
        )
        blob = build_resource_blob(rows, start_sector=10)
        self.assertEqual(blob[:3], b"abc")
        self.assertEqual(blob[SECTOR_BYTES:SECTOR_BYTES + 3], b"xyz")
        self.assertEqual(len(blob), 2 * SECTOR_BYTES)


if __name__ == "__main__":
    unittest.main()
