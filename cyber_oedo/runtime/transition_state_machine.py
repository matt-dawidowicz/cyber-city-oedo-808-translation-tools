"""Direction-specific transition state machine for Mission 0 load latency.

This module consolidates already source-guarded transition findings. It keeps
exploration->dialogue and dialogue->exploration separate so fixed waits from
opposite directions are not accidentally summed into one critical path.
"""

from __future__ import annotations

import argparse
import json
import pathlib

MOVEMENT_OVERLAY_WAIT_FRAMES = 120
MOVEMENT_OVERLAY_WAIT_SECONDS = MOVEMENT_OVERLAY_WAIT_FRAMES / 60.0
BAR_WAIT_FRAMES = 30
BAR_WAIT_SECONDS = BAR_WAIT_FRAMES / 60.0
HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS = (5.7, 6.2)
BAR_COLD_BUTTON_TO_READY_SECONDS = 457 / 60.0
BAR_COLD_LOAD_TO_READY_SECONDS = 370 / 60.0
BAR_WARM_LOAD_TO_READY_SECONDS = 342 / 60.0
BAR_TEARDOWN_FADE_CLEAR_FRAMES = 127
BAR_TEARDOWN_FADE_CLEAR_SECONDS = BAR_TEARDOWN_FADE_CLEAR_FRAMES / 60.0
HISTORICAL_MODE_0E_FADE_SECONDS_APPROX = 2.5


def build_transition_state_machine() -> dict[str, object]:
    return {
        "exploration_to_dialogue": {
            "direction": "interaction/exploration -> dialogue parser",
            "bar_live_measurement": {
                "fixed_wait_frames": BAR_WAIT_FRAMES,
                "fixed_wait_seconds": BAR_WAIT_SECONDS,
                "cold_button_to_parser_seconds": BAR_COLD_BUTTON_TO_READY_SECONDS,
                "cold_loader_to_parser_seconds": BAR_COLD_LOAD_TO_READY_SECONDS,
                "warm_loader_to_parser_seconds": BAR_WARM_LOAD_TO_READY_SECONDS,
                "evidence": (
                    "live bartender replay: CD_FADE $0C followed by a 30-frame "
                    "EX_VSYNC loop in the bar runtime overlay"
                ),
            },
            "other_movement_overlay": {
                "fixed_wait_frames": MOVEMENT_OVERLAY_WAIT_FRAMES,
                "fixed_wait_seconds": MOVEMENT_OVERLAY_WAIT_SECONDS,
                "evidence": "$402B -> $40B1 -> $40DB static call chain",
                "applies_to_bar_measurement": False,
            },
            "historical_first_dialogue_cd_to_parser_seconds": list(
                HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS
            ),
            "interpretation": (
                "The 120-frame $40DB wait is real in another movement-overlay "
                "copy but must not be added to the bartender's 5.7-6.2 second "
                "loader window. The bartender/bar path is independently measured "
                "with a 30-frame wait and 7.617 seconds from Button I to parser."
            ),
        },
        "dialogue_to_exploration": {
            "direction": "dialogue stream end -> exploration interactive loop",
            "phases": [
                {
                    "phase": "dialogue audio fade request",
                    "evidence": "command 2 / CD_FADE mode $0E",
                    "measured_bar_fade_clear_frames": BAR_TEARDOWN_FADE_CLEAR_FRAMES,
                    "measured_bar_fade_clear_seconds": BAR_TEARDOWN_FADE_CLEAR_SECONDS,
                    "historical_api_duration_seconds_approx": (
                        HISTORICAL_MODE_0E_FADE_SECONDS_APPROX
                    ),
                },
                {
                    "phase": "synchronous audio-state gate",
                    "evidence": "$41EC waits for dialogue audio state to clear",
                },
                {
                    "phase": "exploration scene restoration",
                    "evidence": "$228E, $22DE, and VRAM restore path",
                },
            ],
        },
        "optimization_implications": [
            (
                "treat overlay-specific waits separately; do not apply the "
                "120-frame movement-overlay benchmark globally"
            ),
            (
                "resident-module and speaker-local caching attack recurring "
                "bar loader work independently of the 30-frame bar wait"
            ),
            (
                "dialogue return optimization must preserve fade completion and "
                "restore-equivalent VRAM state"
            ),
        ],
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Describe direction-specific Mission 0 transition latency."
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_transition_state_machine()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
