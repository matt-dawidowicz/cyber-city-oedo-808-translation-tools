from __future__ import annotations

import unittest

from cyber_oedo.runtime.load_time_benchmarks import (
    CACHE_INVALIDATE_REPLACEMENT,
    COMMAND0_CACHE_INVALIDATE_EXPECTED,
    COMMAND5_CACHE_INVALIDATE_EXPECTED,
    EXPLORATION_WAIT_EXPECTED,
    RESIDENT_LOADER_EXPECTED,
    RESIDENT_LOADER_REPLACEMENT,
    BAR_PRIMARY_DESCRIPTOR_EXPECTED,
    BAR_PRIMARY_DESCRIPTOR_REPLACEMENT,
    BAR_SELECTIVE_CAVE_REPLACEMENT,
    build_resident_module_benchmark,
    build_short_exploration_wait_benchmark,
    build_speaker_cache_retention_benchmark,
    build_selective_bar_vram_restore_benchmark,
)


class LoadTimeBenchmarkTests(unittest.TestCase):
    def test_resident_loader_patch_preserves_cache_miss_setup(self) -> None:
        self.assertEqual(len(RESIDENT_LOADER_EXPECTED), 12)
        self.assertEqual(len(RESIDENT_LOADER_REPLACEMENT), 12)
        self.assertEqual(
            RESIDENT_LOADER_REPLACEMENT[:8],
            RESIDENT_LOADER_EXPECTED[:8],
        )
        self.assertEqual(RESIDENT_LOADER_REPLACEMENT[8:10], bytes.fromhex("F0 1D"))
        self.assertEqual(RESIDENT_LOADER_REPLACEMENT[10:], bytes.fromhex("64 00"))

    def test_resident_branch_targets_stock_loader_epilogue(self) -> None:
        # Patch begins at $48A6; BEQ operand is at $48AF and branches from
        # the following PC $48B0. $48B0 + $1D = $48CD, the stock PLA.
        self.assertEqual(0x48B0 + RESIDENT_LOADER_REPLACEMENT[9], 0x48CD)

    def test_speaker_cache_retention_only_nops_invalidations(self) -> None:
        benchmark = build_speaker_cache_retention_benchmark()
        self.assertEqual(len(benchmark.patches), 2)
        self.assertEqual(COMMAND0_CACHE_INVALIDATE_EXPECTED, bytes.fromhex("A9 FF 8D DE 8F"))
        self.assertEqual(COMMAND5_CACHE_INVALIDATE_EXPECTED, bytes.fromhex("A9 FF 8D DE 8F"))
        self.assertEqual(CACHE_INVALIDATE_REPLACEMENT, bytes((0xEA,)) * 5)
        self.assertEqual(benchmark.changed_bytes, 10)

    def test_short_wait_default_is_eight_frames(self) -> None:
        benchmark = build_short_exploration_wait_benchmark()
        self.assertEqual(EXPLORATION_WAIT_EXPECTED, bytes.fromhex("A0 78"))
        self.assertEqual(benchmark.patches[0].replacement, bytes.fromhex("A0 08"))
        self.assertEqual(benchmark.changed_bytes, 1)

    def test_short_wait_rejects_zero_and_over_stock(self) -> None:
        for frames in (0, 121, 256):
            with self.assertRaisesRegex(ValueError, "1..120"):
                build_short_exploration_wait_benchmark(frames)

    def test_selective_bar_vram_restore_encodes_two_real_loader_calls(self) -> None:
        benchmark = build_selective_bar_vram_restore_benchmark()
        self.assertEqual(len(benchmark.patches), 3)
        self.assertEqual(BAR_PRIMARY_DESCRIPTOR_EXPECTED, bytes.fromhex("00 E8 22 00 EE"))
        self.assertEqual(BAR_PRIMARY_DESCRIPTOR_REPLACEMENT, bytes.fromhex("00 E8 22 20 8E"))
        self.assertEqual(len(BAR_SELECTIVE_CAVE_REPLACEMENT), 33)
        self.assertTrue(BAR_SELECTIVE_CAVE_REPLACEMENT.endswith(bytes.fromhex("00 01 23 00 1A")))

    def test_all_benchmarks_remain_disabled(self) -> None:
        for benchmark in (
            build_resident_module_benchmark(),
            build_speaker_cache_retention_benchmark(),
            build_short_exploration_wait_benchmark(),
            build_selective_bar_vram_restore_benchmark(),
        ):
            self.assertFalse(benchmark.release_enabled)


if __name__ == "__main__":
    unittest.main()
