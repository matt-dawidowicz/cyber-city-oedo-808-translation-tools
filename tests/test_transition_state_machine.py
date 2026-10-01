from __future__ import annotations

import unittest

from cyber_oedo.runtime.transition_state_machine import (
    BAR_WAIT_SECONDS,
    MOVEMENT_OVERLAY_WAIT_SECONDS,
    build_transition_state_machine,
)


class TransitionStateMachineTests(unittest.TestCase):
    def test_bar_uses_measured_thirty_frame_wait(self) -> None:
        report = build_transition_state_machine()["exploration_to_dialogue"]
        self.assertEqual(BAR_WAIT_SECONDS, 0.5)
        self.assertEqual(report["bar_live_measurement"]["fixed_wait_frames"], 30)
        self.assertAlmostEqual(
            report["bar_live_measurement"]["cold_button_to_parser_seconds"],
            457 / 60.0,
        )

    def test_120_frame_overlay_is_not_added_to_bar_measurement(self) -> None:
        report = build_transition_state_machine()["exploration_to_dialogue"]
        self.assertEqual(MOVEMENT_OVERLAY_WAIT_SECONDS, 2.0)
        self.assertFalse(report["other_movement_overlay"]["applies_to_bar_measurement"])
        self.assertNotIn("candidate_combined_if_ordered_seconds", report)

    def test_analysis_remains_release_disabled(self) -> None:
        self.assertFalse(build_transition_state_machine()["release_enabled"])


if __name__ == "__main__":
    unittest.main()
