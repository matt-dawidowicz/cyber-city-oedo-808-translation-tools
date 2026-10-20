"""Algorithm-independent reference checks for Mode 1 EDC/ECC mathematics.

The oracle uses bitwise GF(2) operations rather than the production lookup
tables. These synthetic vectors complement, but do not replace, verification
against independently sourced real disc sectors.
"""

from __future__ import annotations

import unittest

from cyber_oedo.disc.cdrom_mode1 import (
    MODE1_SYNC,
    compute_edc,
    mode1_integrity_matches,
    rebuild_mode1_sector,
)
from cyber_oedo.disc.game_layout import MODE1_USER_DATA_OFFSET, RAW_SECTOR_SIZE


def reference_edc(data: bytes) -> int:
    """Calculate the reflected CD-ROM EDC polynomial bit by bit."""
    crc = 0
    for octet in data:
        crc ^= octet
        for _ in range(8):
            crc = (crc >> 1) ^ (0xD8018001 if crc & 1 else 0)
    return crc


def gf_double(value: int) -> int:
    """Multiply by x in GF(256), reducing with primitive polynomial 0x11d."""
    result = value * 2
    if result & 0x100:
        result ^= 0x11D
    return result


def gf_halve(value: int) -> int:
    """Find the field element that doubles to the requested value."""
    return next(candidate for candidate in range(256) if gf_double(candidate) == value)


def reference_ecc(
    data: bytes, major_count: int, minor_count: int, multiplier: int, stride: int
) -> bytes:
    """Compute interleaved ECC symbols without production lookup tables."""
    assert len(data) == major_count * minor_count
    parity_a_out = []
    parity_b_out = []
    for major in range(major_count):
        position = (major // 2) * multiplier + (major % 2)
        a = 0
        b = 0
        for _ in range(minor_count):
            byte = data[position]
            position = (position + stride) % len(data)
            a = gf_double(a ^ byte)
            b ^= byte
        a = gf_halve(gf_double(a) ^ b)
        parity_a_out.append(a)
        parity_b_out.append(a ^ b)
    return bytes(parity_a_out + parity_b_out)


class Mode1IndependentReferenceTests(unittest.TestCase):
    """Catch shared integrity implementation mistakes in synthetic sectors."""

    def test_edc_matches_bitwise_reference(self) -> None:
        """Check the CRC algorithm on multiple data patterns and boundaries."""
        for payload in (b"", b"123456789", bytes(range(256)),
                        bytes(range(256)) * 9, bytes(2064)):
            with self.subTest(size=len(payload)):
                self.assertEqual(compute_edc(payload), reference_edc(payload))

    def test_mode1_rebuild_matches_bitwise_reference(self) -> None:
        """Verify independently computed CRC, P parity, and Q parity."""
        raw = bytearray(RAW_SECTOR_SIZE)
        raw[:12] = MODE1_SYNC
        raw[12:15] = bytes((0x12, 0x34, 0x56))
        raw[15] = 1
        raw[MODE1_USER_DATA_OFFSET:2064] = bytes(
            (index * 17 + 23) % 256 for index in range(2048)
        )
        rebuilt = rebuild_mode1_sector(raw)
        self.assertEqual(rebuilt[2064:2068], reference_edc(rebuilt[:2064]).to_bytes(4, "little"))
        self.assertEqual(rebuilt[2068:2076], bytes(8))
        self.assertEqual(
            rebuilt[2076:2248], reference_ecc(rebuilt[12:2076], 86, 24, 2, 86)
        )
        self.assertEqual(
            rebuilt[2248:2352], reference_ecc(rebuilt[12:2248], 52, 43, 86, 88)
        )
        self.assertTrue(mode1_integrity_matches(rebuilt))
        corrupted = bytearray(rebuilt)
        corrupted[MODE1_USER_DATA_OFFSET + 20] ^= 1
        self.assertFalse(mode1_integrity_matches(corrupted))


if __name__ == "__main__":
    unittest.main()
