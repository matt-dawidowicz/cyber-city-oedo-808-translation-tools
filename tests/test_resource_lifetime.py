from __future__ import annotations

import unittest

from cyber_oedo.runtime.resource_lifetime import (
    build_resource_lifetime_report,
    logical_page_geometry,
)


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

    def test_exploration_local_b_splits_across_mpr4_and_mpr5(self) -> None:
        rows = logical_page_geometry(0x9000, 0xA800)
        self.assertEqual(
            rows,
            (
                {
                    "mpr_slot": 4,
                    "logical_start": "$9000",
                    "logical_end_inclusive": "$9FFF",
                    "page_offset_start": "0x1000",
                    "page_offset_end_inclusive": "0x1FFF",
                    "bytes": 0x1000,
                },
                {
                    "mpr_slot": 5,
                    "logical_start": "$A000",
                    "logical_end_inclusive": "$A7FF",
                    "page_offset_start": "0x0000",
                    "page_offset_end_inclusive": "0x07FF",
                    "bytes": 0x0800,
                },
            ),
        )

    def test_page_85_hypothesis_accounts_for_mpr4_and_mpr5_aliases(self) -> None:
        report = build_resource_lifetime_report()
        geometry = report["mpr_geometry"]
        self.assertEqual(geometry["dialogue_workspace_mpr_slot"], 4)
        self.assertEqual(geometry["dialogue_known_physical_page"], "$85")
        self.assertEqual(geometry["module_page_offsets"], ["0x0000", "0x0F50"])
        self.assertEqual(geometry["speaker_page_offsets"], ["0x1000", "0x1FFF"])
        self.assertIn("MPR4", geometry["same_page_hypothesis"])
        self.assertIn("MPR5", geometry["same_page_hypothesis"])
        self.assertIn("clobbers the first 2 KiB", geometry["same_page_hypothesis"])

    def test_report_identifies_exact_runtime_mpr_proof_needed(self) -> None:
        report = build_resource_lifetime_report()
        proof = report["mpr_geometry"]["proof_needed"]
        self.assertIn("MPR4", proof)
        self.assertIn("MPR5", proof)
        self.assertIn("checksum", proof)
        self.assertIn("$22DE", proof)


if __name__ == "__main__":
    unittest.main()
