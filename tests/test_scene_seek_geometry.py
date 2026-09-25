from __future__ import annotations

import unittest

from cyber_oedo.runtime.scene_seek_geometry import build_scene_seek_report


class SceneSeekGeometryTests(unittest.TestCase):
    def test_main_scene_gap_geometry(self) -> None:
        report = build_scene_seek_report()["main_scene"]
        self.assertEqual(report["transfer_sectors"], 40)
        self.assertEqual(report["inter_transfer_gaps_sectors"], 80)
        self.assertEqual(report["absolute_start_distance_sectors"], 90)
        self.assertEqual(report["contiguous_copy_start_distance_sectors"], 10)
        self.assertEqual(
            report["avoidable_start_distance_sectors_if_relocated_contiguously"],
            80,
        )

    def test_main_individual_gaps(self) -> None:
        rows = build_scene_seek_report()["main_scene"]["transitions"]
        self.assertEqual(rows[0]["post_transfer_gap_sectors"], 73)
        self.assertEqual(rows[1]["post_transfer_gap_sectors"], 7)

    def test_alternate_scene_gap_geometry(self) -> None:
        report = build_scene_seek_report()["alternate_scene"]
        self.assertEqual(report["transfer_sectors"], 35)
        self.assertEqual(report["inter_transfer_gaps_sectors"], 5)
        self.assertEqual(report["avoidable_start_distance_sectors_if_relocated_contiguously"], 5)

    def test_analysis_is_not_release_mutation(self) -> None:
        self.assertFalse(build_scene_seek_report()["release_enabled"])


if __name__ == "__main__":
    unittest.main()
