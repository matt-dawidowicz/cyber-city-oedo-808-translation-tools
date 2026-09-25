"""Source-guarded exploration scene-transition architecture.

This module turns the already authenticated movement-overlay regions into an
ordered transition model.  It deliberately separates the explicit audio/wait
gate from scene/room setup and from the blocking CD_READ wrappers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.game_architecture import MOVEMENT_ARCHITECTURE_REGIONS
from cyber_oedo.runtime.movement import MOVEMENT_MODULE_PAYLOAD_BASE

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
    wait_offset = MOVEMENT_MODULE_PAYLOAD_BASE + TRANSITION_WAIT_CPU
    wait_blob = payload[wait_offset : wait_offset + len(TRANSITION_WAIT_BYTES)]

    checks = {
        "transition_wait": wait_blob == TRANSITION_WAIT_BYTES,
        "scene_and_room_setup": hashlib.sha256(setup_blob).hexdigest() == setup.sha256,
        "scene_cd_loaders": hashlib.sha256(loader_blob).hexdigest() == loaders.sha256,
    }
    if not all(checks.values()):
        raise ValueError(f"scene transition source guard mismatch: {checks}")

    return {
        "source_guards": checks,
        "ordered_phases": [
            {
                "phase": "exploration_audio_transition",
                "cpu": "$40DB-$40E8",
                "operation": "CD_FADE mode $0C followed by 120 EX_VSYNC iterations",
                "fixed_frames": 120,
                "fixed_seconds_at_60hz": 2.0,
            },
            {
                "phase": "scene_and_room_setup",
                "cpu": "$40E9-$423A",
                "operation": (
                    "select scene/room descriptors; install collision, entity, "
                    "interaction, and optional spawn state"
                ),
            },
            {
                "phase": "blocking_scene_cd_reads",
                "cpu": "$423B-$428D",
                "operation": (
                    "translate descriptors into System Card CD_READ parameter "
                    "blocks and retry immediately on nonzero status"
                ),
                "contains_explicit_vsync_wait": False,
            },
        ],
        "boundary_facts": {
            "wait_precedes_scene_setup": (
                TRANSITION_WAIT_CPU + len(TRANSITION_WAIT_BYTES)
                == SCENE_SETUP_CPU_START
            ),
            "setup_ends_at_loader_entry": SCENE_SETUP_CPU_END_EXCLUSIVE == SCENE_LOADERS_CPU_START,
            "loader_region_end": f"$%04X" % (SCENE_LOADERS_CPU_END_EXCLUSIVE - 1),
        },
        "optimization_implication": (
            "The 120-frame delay is a distinct high-level transition policy, "
            "not time hidden inside either blocking CD_READ wrapper.  Any "
            "benchmark that shortens the wait can therefore be evaluated "
            "independently from scene-data transfer/layout changes."
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
