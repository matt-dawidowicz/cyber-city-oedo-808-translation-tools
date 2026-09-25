from __future__ import annotations

import unittest

from cyber_oedo.runtime.resource_lifetime import build_resource_lifetime_report


class ResourceLifetimeTests(unittest.TestCase):
    def test_known_scene_load_does_not_logically_overlap_module(self) -> None:
        report = build_resource_lifetime_report()
        self.assertIsNone(
            report["known_exploration_logical_overlap"]["dialogue_module_vs_local_b"]
        )

    def test_known_scene_load_fully_covers_speaker_window(self) -> None:
        report = build_resource_lifetime_report()
        overlap = report["known_exploration_logical_overlap"]["speaker_local_vs_local_b"]
        self.assertIsNotNone(overlap)
        self.assertEqual(overlap["start"], "$9000")
        self.assertEqual(overlap["end_inclusive"], "$9FFF")
        self.assertEqual(overlap["bytes"], 0x1000)
        self.assertTrue(
            report["known_exploration_logical_overlap"]["speaker_window_fully_covered"]
        )

    def test_report_preserves_mpr_caveat(self) -> None:
        report = build_resource_lifetime_report()
        self.assertIn("MPR", report["mpr_caveat"])
        self.assertFalse(report["release_enabled"])


if __name__ == "__main__":
    unittest.main()
