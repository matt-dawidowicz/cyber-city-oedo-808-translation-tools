"""Regression tests for compiled reconnaissance hot paths."""

from __future__ import annotations

import math
import pathlib
import tempfile
import unittest

from cyber_oedo.analysis.disassemble_huc6280 import read_binary_region
from cyber_oedo.analysis.fast_scan import (
    broad_sjis_runs,
    likely_sjis_runs,
    reversed_sjis_runs,
    sector_metrics,
)
from cyber_oedo.analysis.scan_reversed_sjis import scan as scan_reversed
from cyber_oedo.analysis.scan_track import scan_shift_jis
from cyber_oedo.disc.cdrom_mode1 import MODE1_SYNC, rebuild_mode1_sector
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
)


class NativeScanTests(unittest.TestCase):
    """Keep accelerated scanners byte-for-byte deterministic."""

    def test_sector_metrics_match_known_distributions(self) -> None:
        """Compute zero, unique-byte, and entropy values exactly."""

        second = bytes(range(256)) * (SECTOR_SIZE // 256)
        data = bytes(SECTOR_SIZE) + second
        nonzero, unique, entropy, zero = sector_metrics(
            data,
            SECTOR_SIZE,
        )
        self.assertEqual(nonzero.tolist(), [0, SECTOR_SIZE - 8])
        self.assertEqual(unique.tolist(), [1, 256])
        self.assertEqual(zero.tolist(), [True, False])
        self.assertEqual(float(entropy[0]), 0.0)
        self.assertTrue(math.isclose(float(entropy[1]), 8.0))

    def test_broad_scanner_preserves_token_state_machine(self) -> None:
        """Keep Japanese-token counts and run boundaries unchanged."""

        data = "あいうABC".encode("shift_jis") + b"\x00tail"
        starts, ends, japanese = broad_sjis_runs(data, 3)
        self.assertEqual(starts.tolist(), [0])
        self.assertEqual(ends.tolist(), [9])
        self.assertEqual(japanese.tolist(), [3])
        rows = list(scan_shift_jis(data, 3))
        self.assertEqual(rows, [(0, 3, "あいうABC")])

    def test_likely_scanner_rejects_trail_byte_false_positive(self) -> None:
        """Do not restart discovery inside a previously consumed pair."""

        garbage = bytes.fromhex(
            "88 8c 8f 2e 20 4b 67 80 b4 a5 05 48 a5"
        )
        starts, ends, metrics = likely_sjis_runs(garbage, 4)
        self.assertEqual(starts.size, 0)
        self.assertEqual(ends.size, 0)
        self.assertEqual(metrics.shape, (0, 5))

    def test_reversed_scanner_recovers_pair_reversed_text(self) -> None:
        """Recover the same text after each two-byte token is reversed."""

        original = "日本語字幕".encode("shift_jis")
        reversed_bytes = bytearray(len(original))
        reversed_bytes[0::2] = original[1::2]
        reversed_bytes[1::2] = original[0::2]
        starts, ends = reversed_sjis_runs(reversed_bytes, 4)
        self.assertEqual(starts.tolist(), [0])
        self.assertEqual(ends.tolist(), [len(original)])
        self.assertEqual(
            list(scan_reversed(reversed_bytes, 4)),
            [(0, "日本語字幕")],
        )

    def test_bounded_disassembler_reader(self) -> None:
        """Return one requested region and reject zero-length reads."""

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "large.bin"
            path.write_bytes(bytes(range(256)) * 4096)
            self.assertEqual(
                read_binary_region(path, 12345, 4),
                path.read_bytes()[12345:12349],
            )
            with self.assertRaisesRegex(ValueError, "positive"):
                read_binary_region(path, 0, 0)


if __name__ == "__main__":
    unittest.main()
