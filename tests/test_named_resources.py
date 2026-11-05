from __future__ import annotations

import unittest

from cyber_oedo.disc import named_resources as nr
from cyber_oedo.disc.game_layout import TRACK2_START_LBA


def descriptor(name: bytes, lba: int, span: int, length: int) -> bytes:
    return (
        name.ljust(9, b"\0")
        + bytes((lba >> 16,))
        + (lba & 0xFFFF).to_bytes(2, "little")
        + bytes((span,))
        + length.to_bytes(3, "little")
    )


class DescriptorDecodeTests(unittest.TestCase):
    def test_decodes_fields_the_loader_reads(self) -> None:
        row = nr.decode_descriptor(descriptor(b"KURUZER", 0x10F1, 1, 0x320), 0x1377AB)
        self.assertEqual(row.name, "KURUZER")
        self.assertEqual(row.absolute_lba, 0x10F1)
        self.assertEqual(row.relative_sector, 0x10F1 - TRACK2_START_LBA)
        self.assertEqual(row.byte_length, 0x320)
        self.assertEqual(row.mutable_tail_offset, 0x1377AB + 9)

    def test_rejects_invalid_names_and_geometry(self) -> None:
        with self.assertRaisesRegex(nr.NamedResourceError, "invalid name"):
            nr.decode_descriptor(descriptor(b"bad", 0x10F1, 1, 1), 0)
        with self.assertRaisesRegex(nr.NamedResourceError, "outside Track 2"):
            nr.decode_descriptor(descriptor(b"AUDIO", 0x0100, 1, 1), 0)
        with self.assertRaisesRegex(nr.NamedResourceError, "does not fit"):
            nr.decode_descriptor(descriptor(b"BIG", 0x10F1, 1, 0x801), 0)

    def test_reference_scan_finds_descriptors_covering_a_sector(self) -> None:
        payload = bytes(64) + descriptor(b"A1", 0x2000, 2, 0x1000) + bytes(32)
        payload += descriptor(b"B2", 0x3000, 1, 0x10)
        hits = nr.descriptor_references(payload, range(0x2001, 0x2002))
        self.assertEqual(hits, ((64, "A1", 0x2000),))
        self.assertEqual(nr.descriptor_references(payload, range(0x4000, 0x4010)), ())

    def test_find_descriptor_requires_exactly_one_match(self) -> None:
        row = nr.decode_descriptor(descriptor(b"A1", 0x2000, 1, 1), 0)
        self.assertIs(nr.find_descriptor((row,), "A1"), row)
        with self.assertRaisesRegex(nr.NamedResourceError, "exactly one"):
            nr.find_descriptor((row, row), "A1")


class LoaderContractTests(unittest.TestCase):
    def test_heap_bound_matches_loader_comparison(self) -> None:
        self.assertEqual(nr.max_resource_length(0xC350), 0xD800 - 0xC350 - 1)
        with self.assertRaisesRegex(nr.NamedResourceError, "outside the heap"):
            nr.max_resource_length(0xD800)

    def test_loader_guards_fail_closed(self) -> None:
        last = max(cpu + len(expected) for _, cpu, expected in nr.MISSION0_B_LOADER_GUARDS)
        payload = bytearray(nr.MISSION0_B_MODULE_BASE + last)
        for _, cpu, expected in nr.MISSION0_B_LOADER_GUARDS:
            start = nr.MISSION0_B_MODULE_BASE + cpu
            payload[start : start + len(expected)] = expected
        nr.verify_mission0_b_loader(payload)
        payload[nr.MISSION0_B_MODULE_BASE + 0x6D22] ^= 0xFF
        with self.assertRaisesRegex(nr.NamedResourceError, "heap bound check"):
            nr.verify_mission0_b_loader(payload)


if __name__ == "__main__":
    unittest.main()
