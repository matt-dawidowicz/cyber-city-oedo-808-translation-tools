from __future__ import annotations

import unittest

from cyber_oedo.runtime.fast_fade_benchmark import (
    FADE_COMMAND_EXPECTED,
    FADE_COMMAND_PAYLOAD_OFFSET,
    FADE_COMMAND_REPLACEMENT,
    build_fast_fade_benchmark_patch,
)


class FastFadeBenchmarkTests(unittest.TestCase):
    def test_patch_is_same_size_and_starts_with_stop_then_stock_cleanup(self) -> None:
        self.assertEqual(len(FADE_COMMAND_EXPECTED), 25)
        self.assertEqual(len(FADE_COMMAND_REPLACEMENT), 25)
        self.assertEqual(
            FADE_COMMAND_REPLACEMENT[:6],
            bytes.fromhex("20 42 E0 4C 3E 81"),
        )
        self.assertEqual(
            FADE_COMMAND_REPLACEMENT[6:],
            bytes((0xEA,)) * 19,
        )

    def test_payload_offset_targets_module_command_two(self) -> None:
        self.assertEqual(FADE_COMMAND_PAYLOAD_OFFSET, 0x0030F8E7)

    def test_patch_object_preserves_source_length(self) -> None:
        benchmark = build_fast_fade_benchmark_patch()
        self.assertEqual(benchmark.patch.offset, FADE_COMMAND_PAYLOAD_OFFSET)
        self.assertEqual(
            len(benchmark.patch.expected),
            len(benchmark.patch.replacement),
        )
        self.assertGreater(benchmark.changed_bytes, 0)
        self.assertLessEqual(
            benchmark.changed_bytes,
            len(FADE_COMMAND_EXPECTED),
        )


if __name__ == "__main__":
    unittest.main()
