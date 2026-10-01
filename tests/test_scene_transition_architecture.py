from __future__ import annotations

import unittest

from cyber_oedo.registry import command_by_name
from cyber_oedo.runtime.scene_transition_architecture import (
    EXIT_TEARDOWN_BYTES,
    EXIT_TEARDOWN_CPU,
    SCENE_LOADERS_CPU_START,
    SCENE_SETUP_CPU_END_EXCLUSIVE,
    TRANSITION_WAIT_BYTES,
    TRANSITION_WAIT_CPU,
)


class SceneTransitionArchitectureTests(unittest.TestCase):
    def test_exit_teardown_directly_calls_wait(self) -> None:
        self.assertEqual(EXIT_TEARDOWN_CPU, 0x40B1)
        self.assertEqual(EXIT_TEARDOWN_BYTES[:3], bytes.fromhex("20 DB 40"))

    def test_wait_is_address_adjacent_to_scene_orchestration_entry(self) -> None:
        self.assertEqual(TRANSITION_WAIT_CPU + len(TRANSITION_WAIT_BYTES), 0x40E9)

    def test_loader_code_is_address_adjacent_not_a_sequential_phase(self) -> None:
        self.assertEqual(SCENE_SETUP_CPU_END_EXCLUSIVE, SCENE_LOADERS_CPU_START)

    def test_analyzer_is_registered_with_unified_cli(self) -> None:
        spec = command_by_name("analyze-scene-transition")
        self.assertIsNotNone(spec)
        assert spec is not None
        self.assertEqual(
            spec.module,
            "cyber_oedo.runtime.scene_transition_architecture",
        )
        self.assertEqual(spec.group, "Diagnostics")

    def test_wait_is_exactly_120_vsync_frames(self) -> None:
        self.assertEqual(
            TRANSITION_WAIT_BYTES,
            bytes.fromhex("A9 0C 20 2D E0 A0 78 20 7B E0 88 D0 FA 60"),
        )


if __name__ == "__main__":
    unittest.main()
