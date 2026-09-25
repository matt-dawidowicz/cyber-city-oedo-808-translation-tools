from __future__ import annotations

import unittest

from cyber_oedo.runtime.transition_state_machine import (
    EXPLORATION_EXIT_FIXED_WAIT_SECONDS,
    build_transition_state_machine,
)


class TransitionStateMachineTests(unittest.TestCase):
    def test_enter_dialogue_lower_bound_includes_pre_cd_wait(self) -> None:
        report = build_transition_state_machine()["exploration_to_dialogue"]
        self.assertEqual(EXPLORATION_EXIT_FIXED_WAIT_SECONDS, 2.0)
        self.assertEqual(report["combined_lower_bound_seconds"], [7.7, 8.2])

    def test_two_fades_are_assigned_to_different_directions(self) -> None:
        report = build_transition_state_machine()
        enter = report["exploration_to_dialogue"]["phases"]
        leave = report["dialogue_to_exploration"]["phases"]
        self.assertEqual(enter[1]["fixed_wait_seconds"], 2.0)
        self.assertEqual(leave[0]["approximate_fade_seconds"], 2.5)

    def test_analysis_remains_release_disabled(self) -> None:
        self.assertFalse(build_transition_state_machine()["release_enabled"])


if __name__ == "__main__":
    unittest.main()
