from __future__ import annotations

import unittest

from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.named_resources import decode_descriptor
from cyber_oedo.disc.resource_linker import (
    LINK_WINDOW_END_RELATIVE,
    LINK_WINDOW_START_RELATIVE,
    SECTOR_BYTES,
    ResourceObject,
    ResourceLinkError,
    build_resource_blob,
    descriptor_fields,
    link_resources,
    relink_named_resource,
)

SOURCE_RELATIVE = 747
DESCRIPTOR_OFFSET = 0x1000
HEADER = b"KURUZER\x00\x00\x03\x10\x00\x00\x00\x00\x00"
RESOURCE = HEADER + bytes(range(256)) * 3


def synthetic_payload() -> bytearray:
    payload = bytearray(TRACK2_SECTOR_COUNT * SECTOR_BYTES)
    lba = TRACK2_START_LBA + SOURCE_RELATIVE
    payload[DESCRIPTOR_OFFSET : DESCRIPTOR_OFFSET + 16] = (
        b"KURUZER\x00\x00\x00"
        + lba.to_bytes(2, "little")
        + b"\x01"
        + len(RESOURCE).to_bytes(3, "little")
    )
    start = SOURCE_RELATIVE * SECTOR_BYTES
    payload[start : start + len(RESOURCE)] = RESOURCE
    return payload


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


class NamedResourceRelinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = synthetic_payload()
        cls.descriptor = decode_descriptor(
            bytes(cls.payload[DESCRIPTOR_OFFSET : DESCRIPTOR_OFFSET + 16]), DESCRIPTOR_OFFSET
        )

    def test_grown_resource_is_placed_in_window_and_descriptor_repointed(self) -> None:
        grown = RESOURCE + b"\xAA" * 3000
        relink = relink_named_resource(self.payload, self.descriptor, grown, load_address=0xC350)
        self.assertEqual(relink.relative_sector, LINK_WINDOW_START_RELATIVE)
        self.assertEqual(relink.linked.sector_span, 2)
        lba = TRACK2_START_LBA + LINK_WINDOW_START_RELATIVE
        self.assertEqual(
            relink.descriptor_tail,
            b"\x00" + lba.to_bytes(2, "little") + b"\x02" + len(grown).to_bytes(3, "little"),
        )
        data_patch, descriptor_patch = relink.patches
        self.assertEqual(data_patch.offset, LINK_WINDOW_START_RELATIVE * SECTOR_BYTES)
        self.assertEqual(data_patch.expected, bytes(2 * SECTOR_BYTES))
        self.assertEqual(data_patch.replacement[: len(grown)], grown)
        self.assertEqual(descriptor_patch.offset, DESCRIPTOR_OFFSET + 9)
        self.assertEqual(descriptor_patch.expected, self.descriptor.raw[9:])

    def test_header_change_is_rejected(self) -> None:
        with self.assertRaisesRegex(ResourceLinkError, "16-byte header"):
            relink_named_resource(
                self.payload, self.descriptor, b"X" + RESOURCE[1:], load_address=0xC350
            )

    def test_heap_bound_is_enforced(self) -> None:
        too_long = RESOURCE + bytes(0xD800 - 0xC350 - len(RESOURCE))
        with self.assertRaisesRegex(ResourceLinkError, "heap bound"):
            relink_named_resource(self.payload, self.descriptor, too_long, load_address=0xC350)

    def test_nonzero_or_named_target_sectors_are_rejected(self) -> None:
        payload = bytearray(self.payload)
        payload[LINK_WINDOW_START_RELATIVE * SECTOR_BYTES + 5] = 1
        with self.assertRaisesRegex(ResourceLinkError, "zero fill"):
            relink_named_resource(payload, self.descriptor, RESOURCE, load_address=0xC350)
        payload = bytearray(self.payload)
        lba = TRACK2_START_LBA + LINK_WINDOW_START_RELATIVE
        payload[0x2000:0x2010] = (
            b"OTHER\x00\x00\x00\x00\x00" + lba.to_bytes(2, "little") + b"\x01\x10\x00\x00"
        )
        with self.assertRaisesRegex(ResourceLinkError, "already named"):
            relink_named_resource(payload, self.descriptor, RESOURCE, load_address=0xC350)

    def test_window_cannot_be_widened(self) -> None:
        with self.assertRaisesRegex(ResourceLinkError, "outside the owned"):
            relink_named_resource(
                self.payload, self.descriptor, RESOURCE, load_address=0xC350,
                window_end_relative=LINK_WINDOW_END_RELATIVE + 1,
            )


if __name__ == "__main__":
    unittest.main()
