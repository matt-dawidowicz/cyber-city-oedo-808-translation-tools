"""Source-guarded exploration scene-transition architecture.

This module turns the already authenticated movement-overlay regions into a
transition-layout model. It identifies the explicit audio/wait routine and
scene/room orchestration by address while deliberately avoiding a runtime-order
claim until the relevant caller/control flow is authenticated. Blocking CD_READ
wrappers are treated as nested callees, not as a later sequential phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.game_architecture import MOVEMENT_ARCHITECTURE_REGIONS
from cyber_oedo.runtime.movement import MOVEMENT_MODULE_PAYLOAD_BASE

EXPLORATION_EXIT_CALL_CPU = 0x402B
EXPLORATION_RETURN_CPU = 0x403C
EXIT_TEARDOWN_CPU = 0x40B1
EXIT_TEARDOWN_BYTES = bytes.fromhex(
    "20 DB 40 20 99 E0 9C 0C 22 9C 0D 22 9C 10 22 9C 11 22 "
    "20 7B E0 03 07 9C 02 00 9C 03 00 03 08 9C 02 00 9C 03 "
    "00 62 20 69 E0 60"
)
TRANSITION_WAIT_CPU = 0x40DB
TRANSITION_WAIT_BYTES = bytes.fromhex(
    "A9 0C 20 2D E0 A0 78 20 7B E0 88 D0 FA 60"
)
SCENE_SETUP_CPU_START = 0x40E9
SCENE_SETUP_CPU_END_EXCLUSIVE = 0x423B
SCENE_LOADERS_CPU_START = 0x423B
SCENE_LOADERS_CPU_END_EXCLUSIVE = 0x428E


def _region(name: str):
    return next(item for item in MOVEMENT_ARCHITECTURE_REGIONS if item.name == name)


def analyze_scene_transition_architecture(payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            f"payload SHA-256 mismatch: expected {TRACK2_PAYLOAD_SHA256}, got {digest}"
        )

    setup = _region("scene_and_room_setup")
    loaders = _region("scene_cd_loaders")
    setup_blob = payload[setup.payload_offset : setup.payload_offset + setup.length]
    loader_blob = payload[loaders.payload_offset : loaders.payload_offset + loaders.length]
    exit_offset = MOVEMENT_MODULE_PAYLOAD_BASE + EXIT_TEARDOWN_CPU
    exit_blob = payload[exit_offset : exit_offset + len(EXIT_TEARDOWN_BYTES)]
    wait_offset = MOVEMENT_MODULE_PAYLOAD_BASE + TRANSITION_WAIT_CPU
    wait_blob = payload[wait_offset : wait_offset + len(TRANSITION_WAIT_BYTES)]

    checks = {
        "exit_teardown": exit_blob == EXIT_TEARDOWN_BYTES,
        "transition_wait": wait_blob == TRANSITION_WAIT_BYTES,
        "scene_and_room_setup": hashlib.sha256(setup_blob).hexdigest() == setup.sha256,
        "scene_cd_loaders": hashlib.sha256(loader_blob).hexdigest() == loaders.sha256,
    }
    if not all(checks.values()):
        raise ValueError(f"scene transition source guard mismatch: {checks}")

    return {
        "source_guards": checks,
        "proven_exit_call_chain": {
            "loop_exit_call_site": "$402B JSR $40B1",
            "exit_teardown_entry": "$40B1 JSR $40DB",
            "wait_routine": "$40DB-$40E8",
            "exploration_return": "$403C RTS",
            "statement": (
                "The authenticated exploration loop directly calls $40B1 at $402B; "
                "$40B1 directly calls the 120-frame wait at $40DB before returning. "
                "Thus the wait is proven on this exploration-exit path."
            ),
        },
        "address_ordered_regions": [
            {
                "phase": "exploration_audio_transition",
                "cpu": "$40DB-$40E8",
                "operation": "CD_FADE mode $0C followed by 120 EX_VSYNC iterations",
                "fixed_frames": 120,
                "fixed_seconds_at_60hz": 2.0,
            },
            {
                "phase": "scene_and_room_orchestration",
                "cpu_region": "$40E9-$423A",
                "operation": (
                    "select scene/room descriptors; install collision, entity, "
                    "interaction, optional spawn state, and call resource loaders"
                ),
            },
        ],
        "nested_resource_loaders": [
            {
                "cpu": "$423B-$4261",
                "role": "local-memory CD_READ wrapper",
                "nested_within": "scene_and_room_orchestration",
                "contains_explicit_vsync_wait": False,
            },
            {
                "cpu": "$4262-$428D",
                "role": "VRAM CD_READ wrapper",
                "nested_within": "scene_and_room_orchestration",
                "contains_explicit_vsync_wait": False,
            },
        ],
        "address_layout_facts": {
            "wait_ends_at_orchestration_entry": (
                TRANSITION_WAIT_CPU + len(TRANSITION_WAIT_BYTES)
                == SCENE_SETUP_CPU_START
            ),
            "loader_code_is_adjacent_after_setup_region": (
                SCENE_SETUP_CPU_END_EXCLUSIVE == SCENE_LOADERS_CPU_START
            ),
            "adjacency_is_not_runtime_ordering": True,
            "wait_to_orchestration_runtime_order_proven": False,
            "scene_orchestration_is_entry_path_not_exit_chain": True,
            "loader_region_end": f"$%04X" % (SCENE_LOADERS_CPU_END_EXCLUSIVE - 1),
        },
        "optimization_implication": (
            "The 120-frame routine is proven on the exploration-exit path via "
            "$402B -> $40B1 -> $40DB. $40E9 belongs to the scene-entry/setup path "
            "and must not be inserted into the exit-to-dialogue sequence merely "
            "because its code follows $40DB in memory. The remaining timing gate "
            "is whether the exploration return at $403C is followed by the $1425 "
            "dialogue loader on the measured interaction."
        ),
        "runtime_order_gate": (
            "Observe $402B -> $40DB -> $403C -> $1425 byte loader -> $9543 parser "
            "in one interaction before adding the 120 frames to the historical "
            "first-CD-to-parser budget."
        ),
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Cyber City Oedo 808 scene-transition phase boundaries."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = analyze_scene_transition_architecture(args.payload.read_bytes())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
