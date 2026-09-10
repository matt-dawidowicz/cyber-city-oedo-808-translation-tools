"""Synthetic regression coverage for optimized binary I/O paths."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

from cyber_oedo.build.image_verify import (
    compare_and_hash_raw_images,
    verify_output_patches,
)
from cyber_oedo.disc.cdrom_mode1 import (
    MODE1_SYNC,
    PayloadPatch,
    mode1_integrity_matches,
    rebuild_mode1_sector,
)
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
)
from cyber_oedo.disc.patching import apply_payload_patches


def synthetic_sector(fill: int) -> bytes:
    """Return one valid Mode 1 sector filled with a payload byte."""

    raw = bytearray(RAW_SECTOR_SIZE)
    raw[: len(MODE1_SYNC)] = MODE1_SYNC
    raw[15] = 1
    raw[MODE1_USER_DATA_OFFSET : MODE1_USER_DATA_OFFSET + SECTOR_SIZE] = (
        bytes((fill,)) * SECTOR_SIZE
    )
    return rebuild_mode1_sector(raw)


class OptimizedPatchingTests(unittest.TestCase):
    """Keep sector-indexed patching equivalent to guarded raw patching."""

    def test_cross_sector_patch_rebuilds_both_sectors(self) -> None:
        """Apply one guarded patch spanning a payload sector boundary."""

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "test.img"
            path.write_bytes(synthetic_sector(0x11) + synthetic_sector(0x22))
            patch = PayloadPatch(
                offset=SECTOR_SIZE - 2,
                expected=b"\x11\x11\x22\x22",
                replacement=b"ABCD",
                label="boundary",
            )
            reports = apply_payload_patches(
                path,
                (patch,),
                start_lba=0,
                sector_count=2,
            )
            self.assertEqual(
                [report.relative_sector for report in reports],
                [0, 1],
            )
            raw = path.read_bytes()
            first = raw[:RAW_SECTOR_SIZE]
            second = raw[RAW_SECTOR_SIZE:]
            self.assertTrue(mode1_integrity_matches(first))
            self.assertTrue(mode1_integrity_matches(second))
            self.assertEqual(
                first[
                    MODE1_USER_DATA_OFFSET + SECTOR_SIZE - 2 : MODE1_USER_DATA_OFFSET
                    + SECTOR_SIZE
                ],
                b"AB",
            )
            self.assertEqual(
                second[MODE1_USER_DATA_OFFSET : MODE1_USER_DATA_OFFSET + 2],
                b"CD",
            )

    def test_verifier_reads_back_replacements(self) -> None:
        """Verify several patches sharing one sector after application."""

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "test.img"
            path.write_bytes(synthetic_sector(0x33))
            patches = (
                PayloadPatch(10, b"\x33\x33", b"XY", "first"),
                PayloadPatch(30, b"\x33\x33", b"ZZ", "second"),
            )
            apply_payload_patches(
                path,
                patches,
                start_lba=0,
                sector_count=1,
            )
            verify_output_patches(path, patches, start_lba=0)


class ChunkedImageComparisonTests(unittest.TestCase):
    """Verify combined compare and hashing semantics."""

    def test_compare_finds_exact_lba_and_output_hash(self) -> None:
        """Hash output while reporting only its changed raw sector."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "source.img"
            output = root / "output.img"
            source_data = (
                synthetic_sector(0x10) + synthetic_sector(0x20) + synthetic_sector(0x30)
            )
            changed = bytearray(source_data)
            changed[RAW_SECTOR_SIZE + 100] ^= 0x01
            source.write_bytes(source_data)
            output.write_bytes(changed)
            result = compare_and_hash_raw_images(
                source,
                output,
                chunk_sectors=2,
            )
            self.assertEqual(result.changed_lbas, (1,))
            self.assertEqual(
                result.output_sha256,
                hashlib.sha256(changed).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
