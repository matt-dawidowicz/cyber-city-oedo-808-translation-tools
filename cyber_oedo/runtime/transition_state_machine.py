"""Direction-specific transition state machine for Mission 0 load latency.

This module consolidates already source-guarded transition findings. It keeps
exploration->dialogue and dialogue->exploration separate so fixed waits from
opposite directions are not accidentally summed into one critical path.
"""

from __future__ import annotations

import argparse
import json
import pathlib

EXPLORATION_EXIT_FIXED_WAIT_FRAMES = 120
EXPLORATION_EXIT_FIXED_WAIT_SECONDS = EXPLORATION_EXIT_FIXED_WAIT_FRAMES / 60.0
HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS = (5.7, 6.2)
DIALOGUE_TEARDOWN_FADE_SECONDS_APPROX = 2.5


def build_transition_state_machine() -> dict[str, object]:
    enter_min = (
        HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS[0]
        + EXPLORATION_EXIT_FIXED_WAIT_SECONDS
    )
    enter_max = (
        HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS[1]
        + EXPLORATION_EXIT_FIXED_WAIT_SECONDS
    )
    return {
        "exploration_to_dialogue": {
            "direction": "interaction/exploration -> dialogue parser",
            "phases": [
                {
                    "phase": "interaction exit",
                    "evidence": "$2649 exit flag / $402B movement transition path",
                    "timing": "not separately measured",
                },
                {
                    "phase": "exploration audio fade policy",
                    "evidence": (
                        "$40DB routine: CD_FADE mode $0C followed by "
                        "LDY #$78 / EX_VSYNC loop"
                    ),
                    "fixed_wait_frames": EXPLORATION_EXIT_FIXED_WAIT_FRAMES,
                    "fixed_wait_seconds": EXPLORATION_EXIT_FIXED_WAIT_SECONDS,
                },
                {
                    "phase": "dialogue optical/resource setup",
                    "evidence": (
                        "$1425 module load, optional 10xx event resource, "
                        "speaker local/ADPCM source, portrait/UI"
                    ),
                    "timing": "included in historical load-to-ready window",
                },
                {
                    "phase": "dialogue ready",
                    "evidence": "first parser execution",
                },
            ],
            "historical_first_dialogue_cd_to_parser_seconds": list(
                HISTORICAL_DIALOGUE_LOAD_TO_READY_SECONDS
            ),
            "static_fixed_wait_before_that_window_seconds": (
                EXPLORATION_EXIT_FIXED_WAIT_SECONDS
            ),
            "combined_lower_bound_seconds": [enter_min, enter_max],
            "interpretation": (
                "The historical 5.7-6.2 second timer starts at the first "
                "dialogue-related CD request, so the preceding 120-frame "
                "exploration exit wait is outside it. The visible interaction "
                "latency is therefore already at least about 7.7-8.2 seconds "
                "before smaller pre-read/setup costs are assigned."
            ),
        },
        "dialogue_to_exploration": {
            "direction": "dialogue stream end -> exploration interactive loop",
            "phases": [
                {
                    "phase": "dialogue audio fade request",
                    "evidence": (
                        "dialogue command 2 at $80E7 invokes CD_FADE mode $0E "
                        "when $37F0 is active"
                    ),
                    "approximate_fade_seconds": DIALOGUE_TEARDOWN_FADE_SECONDS_APPROX,
                },
                {
                    "phase": "synchronous audio-state gate",
                    "evidence": (
                        "outer transition waits at $41EC while $420B is set "
                        "until periodic dialogue audio state clears $37F0"
                    ),
                    "timing": (
                        "overlaps/implements completion of the fade state; do "
                        "not add another 2.5 seconds without live timing"
                    ),
                },
                {
                    "phase": "dialogue cleanup",
                    "evidence": (
                        "command 5 clears audio state and invalidates speaker "
                        "metadata in the shipping path"
                    ),
                },
                {
                    "phase": "exploration scene installation",
                    "evidence": (
                        "scene/room setup plus known $228E, $22DE, $22E8 hot "
                        "bundle on the main scene"
                    ),
                },
                {
                    "phase": "display/object/music initialization",
                    "evidence": (
                        "room pointers, objects/collision, VRAM/BAT/display "
                        "state, and exploration CD-DA restart before control"
                    ),
                    "timing": "not yet fully partitioned",
                },
            ],
            "interpretation": (
                "The ~2.5-second-class dialogue fade belongs to the return to "
                "exploration, not to the earlier 120-frame exploration-exit "
                "wait. Treating both as one direction double-counts two "
                "different state-machine legs."
            ),
        },
        "optimization_implications": [
            (
                "exploration->dialogue can save a deterministic 1.87 seconds "
                "by benchmarking 120 frames versus the current 8-frame short-wait "
                "prototype, independent of optical caching"
            ),
            (
                "dialogue->exploration audio teardown must preserve completion "
                "semantics; use the existing immediate-cleanup benchmark rather "
                "than simply deleting the $41EC gate"
            ),
            (
                "module/portrait/audio caching attacks the 5.7-6.2 second "
                "post-first-CD portion, while the 120-frame benchmark attacks "
                "latency before that measurement window"
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
