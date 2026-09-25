"""Map same-room exploration state that stock scene re-entry reinstalls.

This diagnostic is deliberately conservative.  It distinguishes fields whose
write behavior is proven by source-guarded movement routines from higher-level
questions that still require runtime evidence, such as whether every dialogue
return invokes object initialization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.movement import MOVEMENT_REGIONS


def _region(name: str):
    return next(item for item in MOVEMENT_REGIONS if item.name == name)


def analyze_same_room_reentry(payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            f"payload SHA-256 mismatch: expected {TRACK2_PAYLOAD_SHA256}, got {digest}"
        )

    names = (
        "scene_result_promotion",
        "scene_entry_selection",
        "object_source_initialization",
        "collision_rectangle_registry",
    )
    checks: dict[str, bool] = {}
    for name in names:
        item = _region(name)
        blob = payload[item.payload_offset : item.payload_offset + len(item.expected)]
        checks[name] = blob == item.expected
    if not all(checks.values()):
        raise ValueError(f"same-room source guard mismatch: {checks}")

    return {
        "source_guards": checks,
        "scene_selection_contract": {
            "active_scene": "$3700",
            "active_entry": "$3701",
            "position_mode": "$3702",
            "transition_payload": "$3703-$370B",
            "ff_transition_behavior": (
                "$3703==FF promotes $3704/$3705/$3706 into $3700/$3701/$3702"
            ),
        },
        "entry_record_installation": {
            "player_xy": {
                "destination": "$2760-$2763",
                "condition": "$3702==0",
                "preserved_when": "$3702!=0",
            },
            "always_reinstalled": [
                {
                    "field": "room_feature",
                    "destination": "$264C",
                    "entry_offset": "+4",
                },
                {
                    "field": "object_source_pointer",
                    "destination": "$277E/$277F",
                    "entry_offset": "+5/+6",
                },
                {
                    "field": "interaction_table_pointer",
                    "destination": "$2779/$277A",
                    "entry_offset": "+7/+8",
                },
                {
                    "field": "room_loader_parameter_a",
                    "destination": "zero page $1E/$1F",
                    "entry_offset": "+9/+10",
                },
                {
                    "field": "room_loader_parameter_b",
                    "destination": "$421E/$421F",
                    "entry_offset": "+11/+12",
                },
            ],
            "important_asymmetry": (
                "The stock entry selector already has an explicit preservation "
                "policy for player position, but no equivalent same-room guard "
                "around the object/interaction/loader fields in this routine."
            ),
        },
        "mutable_exploration_state_at_risk_if_reinitialized": {
            "live_objects": {
                "count": "$277D",
                "records": "$2783 + index*16",
                "effect": (
                    "object_source_initialization rebuilds live records from the "
                    "compact source table, including animation/runtime state"
                ),
            },
            "occupancy_rectangles": {
                "count": "$265D",
                "base": "$265E",
                "effect": (
                    "the rectangle registry has an explicit count-reset entry and "
                    "is populated during object initialization"
                ),
            },
            "camera_and_scroll": {
                "scroll_x": "$220C/$220D",
                "scroll_y": "$2210/$2211",
                "classification": (
                    "mutable exploration state; no source proof here that dialogue "
                    "requires it to be reconstructed on same-room return"
                ),
            },
        },
        "fast_return_design": {
            "safe_static_statement": (
                "A same-room fast path cannot be defined as merely skipping the "
                "60,928-byte VRAM read. It must preserve or deliberately reinstall "
                "the entry-record fields and must decide whether live object and "
                "occupancy state should survive."
            ),
            "candidate_preserve_set": [
                "$2760-$2763 player position",
                "$277D/$2783... live object runtime",
                "$265D/$265E... occupancy rectangles",
                "$220C/$2210 camera scroll state",
            ],
            "candidate_reinstall_set": [
                "$264C room feature",
                "$277E/$277F object-source pointer",
                "$2779/$277A interaction pointer",
                "room loader parameters",
            ],
            "runtime_gate": (
                "prove which of object initialization, collision/occupancy rebuild, "
                "camera setup, and display enable actually execute on a representative "
                "dialogue->same-room return before suppressing them"
            ),
        },
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map same-room exploration re-entry state and preservation candidates."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = analyze_same_room_reentry(args.payload.read_bytes())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
