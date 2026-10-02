from __future__ import annotations

import unittest

from cyber_oedo.runtime.combined_fast_load_benchmark import (
    build_combined_bar_benchmark,
)


class CombinedFastLoadBenchmarkTests(unittest.TestCase):
    def test_core_stack_is_non_overlapping(self) -> None:
        result = build_combined_bar_benchmark()
        result.assert_non_overlapping()
        self.assertFalse(result.aggressive)
        self.assertGreaterEqual(len(result.patches), 9)
        self.assertGreater(result.changed_bytes, 0)

    def test_aggressive_stack_adds_two_independent_experiments(self) -> None:
        core = build_combined_bar_benchmark()
        aggressive = build_combined_bar_benchmark(aggressive=True)
        aggressive.assert_non_overlapping()
        self.assertTrue(aggressive.aggressive)
        self.assertEqual(len(aggressive.patches), len(core.patches) + 2)

    def test_other_overlay_120_frame_patch_is_not_composed(self) -> None:
        result = build_combined_bar_benchmark(aggressive=True)
        labels = " ".join(patch.label.lower() for patch in result.patches)
        self.assertNotIn("120-frame", labels)
        self.assertNotIn("exploration wait", labels)


if __name__ == "__main__":
    unittest.main()
