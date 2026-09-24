"""Source-guarded static evidence for the exploration movement engine."""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256


MOVEMENT_MODULE_PAYLOAD_BASE = 0x000A4800
INPUT_DECODER_CPU = 0x46F2
INPUT_UPDATE_CPU = 0x51E0
DIRECTION_FILTER_CPU = 0x52AA
MOVEMENT_DISPATCH_CPU = 0x52F2
STEP_COMMIT_CPU = 0x4A9E
UNIT_VECTOR_CPU = 0x5DC5
TILE_VECTOR_CPU = 0x5DA7

PLAYER_X = 0x2760
PLAYER_Y = 0x2762
INPUT_CURRENT = 0x276C
INPUT_PREVIOUS = 0x276D
DIRECTION_CURRENT = 0x276E
DIRECTION_PREVIOUS = 0x276F
STEP_X = 0x2767
STEP_Y = 0x2768
STEP_TIMER = 0x2769

INPUT_CODES = {
    1: "left",
    2: "down",
    3: "right",
    4: "up",
    5: "run",
    6: "select",
    7: "II",
    8: "I",
}
UNIT_VECTORS = {
    1: (-1, 0),
    2: (0, 1),
    3: (1, 0),
    4: (0, -1),
}
TILE_VECTORS = {
    1: (-16, 0),
    2: (0, 16),
    3: (16, 0),
    4: (0, -16),
}


@dataclass(frozen=True, slots=True)
class MovementRegion:
    name: str
    cpu_address: int
    expected: bytes
    purpose: str

    @property
    def payload_offset(self) -> int:
        return MOVEMENT_MODULE_PAYLOAD_BASE + self.cpu_address


MOVEMENT_REGIONS = (
    MovementRegion(
        "input_decoder",
        INPUT_DECODER_CPU,
        bytes.fromhex(
            "AD 28 22 82 0A B0 07 E8 E0 08 D0 F8 62 60 "
            "BD 04 47 60 01 02 03 04 05 06 07 08"
        ),
        (
            "Read System Card JOY state at $2228, scan bits from bit 7 to bit 0, "
            "and normalize the first set bit to codes 1..8."
        ),
    ),
    MovementRegion(
        "input_update",
        INPUT_UPDATE_CPU,
        bytes.fromhex("AD 6C 27 8D 6D 27 20 F2 46 8D 6C 27 60"),
        "Move current input to previous input, decode JOY, and store new input.",
    ),
    MovementRegion(
        "direction_filter",
        DIRECTION_FILTER_CPU,
        bytes.fromhex(
            "AD 6C 27 C9 05 90 01 62 8D 6E 27 "
            "AD 6D 27 C9 05 90 01 62 8D 6F 27 60"
        ),
        (
            "Retain only direction codes 1..4 for current and previous "
            "movement direction."
        ),
    ),
    MovementRegion(
        "movement_dispatch",
        MOVEMENT_DISPATCH_CPU,
        bytes.fromhex(
            "A5 1C 48 A5 1D 48 A5 1E 48 A5 1F 48 "
            "20 F6 53 20 09 54 90 05 20 C1 52 80 24 "
            "EE 6B 27 20 5C 53 AD 6F 27 CD 6E 27 F0 03 20 3C 53 "
            "A9 00 8D 7B 27 20 20 4B A9 10 8D 69 27 "
            "20 9E 4A 20 69 54"
        ),
        (
            "Prepare a unit direction, gate movement through the pre-move "
            "collision/occupancy test, update direction/animation state, set "
            "a 16-step timer, commit one step, and perform target probing."
        ),
    ),
    MovementRegion(
        "step_commit",
        STEP_COMMIT_CPU,
        bytes.fromhex(
            "CE 69 27 AD 67 27 49 80 0A 62 E9 00 48 "
            "AD 60 27 18 6D 67 27 8D 60 27 68 6D 61 27 8D 61 27 "
            "AD 68 27 49 80 0A 62 E9 00 48 "
            "AD 62 27 18 6D 68 27 8D 62 27 68 6D 63 27 8D 63 27 "
            "20 DB 4A 60"
        ),
        (
            "Decrement the 16-step movement timer and add signed unit X/Y "
            "deltas to the 16-bit player position pairs."
        ),
    ),
)


def validate_movement_regions(payload: pathlib.Path) -> tuple[dict[str, Any], ...]:
    results: list[dict[str, Any]] = []
    with payload.open("rb") as source:
        for region in MOVEMENT_REGIONS:
            source.seek(region.payload_offset)
            actual = source.read(len(region.expected))
            results.append(
                {
                    "name": region.name,
                    "cpu_address": f"0x{region.cpu_address:04X}",
                    "payload_offset": f"0x{region.payload_offset:08X}",
                    "bytes": len(region.expected),
                    "matched": actual == region.expected,
                    "purpose": region.purpose,
                }
            )
    return tuple(results)


def build_movement_report(payload: pathlib.Path) -> dict[str, Any]:
    digest = sha256_file(payload)
    regions = validate_movement_regions(payload)
    return {
        "tier": "B-movement-static",
        "scope": "exploration input and player movement candidate module",
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "all_source_guards_match": all(item["matched"] for item in regions),
        "regions": regions,
        "state": {
            "player_x": "$2760/$2761",
            "player_y": "$2762/$2763",
            "input_current": "$276C",
            "input_previous": "$276D",
            "direction_current": "$276E",
            "direction_previous": "$276F",
            "step_x": "$2767",
            "step_y": "$2768",
            "step_timer": "$2769",
        },
        "input_codes": INPUT_CODES,
        "unit_vectors": {str(key): value for key, value in UNIT_VECTORS.items()},
        "tile_vectors": {str(key): value for key, value in TILE_VECTORS.items()},
        "limits": {
            "proof_level": "static source-guarded",
            "module_load_mapping": (
                "CPU-relative layout is internally self-consistent; live MPR "
                "capture is still required to certify the runtime bank identity"
            ),
            "collision_semantics": (
                "movement is carry-gated through $5409/$490A before commit; "
                "the underlying map/collision representation needs further proof"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate source-guarded static exploration movement evidence."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_movement_report(args.payload)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["payload_authenticated"] and report["all_source_guards_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
