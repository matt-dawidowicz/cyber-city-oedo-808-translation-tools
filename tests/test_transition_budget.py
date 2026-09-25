from __future__ import annotations

import unittest

from cyber_oedo.runtime.transition_budget import parse_transition_budgets


class TransitionBudgetTests(unittest.TestCase):
    def test_parses_and_validates_budget(self) -> None:
        text = (
            "[TRANSITION_BUDGET] start_frame=10 ready_frame=310 total_frames=300 total_seconds=5.0000 "
            "cd_read_frames=60 cd_read_calls=3 cd_exec_frames=30 cd_exec_calls=1 "
            "ad_trans_frames=20 ad_trans_calls=1 ad_read_frames=10 ad_read_calls=1 "
            "ad_write_frames=10 ad_write_calls=1 fade_wait_frames=120 vsync_calls=128 "
            "known_serial_frames=250 residual_frames=50"
        )
        report = parse_transition_budgets(text)
        row = report["transitions"][0]
        self.assertEqual(row["total_seconds"], 5.0)
        self.assertEqual(row["fade_wait_seconds"], 2.0)
        self.assertEqual(row["residual_frames"], 50)

    def test_rejects_inconsistent_known_sum(self) -> None:
        text = (
            "[TRANSITION_BUDGET] total_frames=100 "
            "cd_read_frames=10 cd_read_calls=1 cd_exec_frames=0 cd_exec_calls=0 "
            "ad_trans_frames=0 ad_trans_calls=0 ad_read_frames=0 ad_read_calls=0 "
            "ad_write_frames=0 ad_write_calls=0 fade_wait_frames=20 vsync_calls=20 "
            "known_serial_frames=99 residual_frames=1"
        )
        with self.assertRaisesRegex(ValueError, "known_serial_frames"):
            parse_transition_budgets(text)


if __name__ == "__main__":
    unittest.main()
