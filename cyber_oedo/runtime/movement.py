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
ANIMATION_COUNTDOWN = 0x2764
ANIMATION_SCRIPT_POINTER = 0x2765
COLLISION_BITMAP_BASE = 0x275E
MAP_WIDTH_TILES = 0x264A
COLLISION_RECT_COUNT = 0x265D
COLLISION_RECT_BASE = 0x265E
INTERACTION_TABLE_POINTER = 0x2779
INTERACTION_CLASS = 0x277B
INTERACTION_RESULT = 0x3703

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

WALK_ANIMATION_SCRIPTS = {
    1: 0x4649,
    2: 0x4654,
    3: 0x465F,
    4: 0x466A,
}
IDLE_ANIMATION_SCRIPTS = {
    1: 0x4675,
    2: 0x467A,
    3: 0x467F,
    4: 0x4684,
}
INTERACTION_RECORD_BYTES = 18
INTERACTION_BOUNDS_BYTES = 8
INTERACTION_PAYLOAD_BYTES = 9
COLLISION_RECT_BYTES = 8


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
    MovementRegion(
        "collision_bitmap_lookup",
        0x490A,
        bytes.fromhex(
            "A5 1C 48 A5 1D 48 A5 1E 48 A5 1F 48 20 56 49 "
            "A5 20 49 80 0A 62 E9 00 48 A5 1C 18 65 20 85 1C "
            "68 65 1D 85 1D A5 21 49 80 0A 62 E9 00 48 A5 1E "
            "18 65 21 85 1E 68 65 1F 85 1F 20 77 49 20 CC 49 "
            "68 85 1F 68 85 1E 68 85 1D 68 85 1C 60 "
            "46 1D 66 1C 46 1D 66 1C 46 1D 66 1C 46 1D 66 1C "
            "46 1F 66 1E 46 1F 66 1E 46 1F 66 1E 46 1F 66 1E 60 "
            "A5 1C 48 A5 1D 48 A5 1E 85 F8 AD 4A 26 85 FA 20 BD E0 "
            "A5 FC 85 1E A5 FD 85 1F 46 1F 66 1E 46 1F 66 1E "
            "46 1F 66 1E 46 1D 66 1C 46 1D 66 1C 46 1D 66 1C "
            "A5 1E 18 65 1C 85 1E A5 1F 65 1D 85 1F "
            "A5 1E 18 6D 5E 27 85 1E A5 1F 6D 5F 27 85 1F "
            "68 85 1D 68 85 1C 60 A5 1C 29 07 A8 B2 1E 85 1C "
            "98 F0 05 06 1C 88 80 F8 06 1C 60"
        ),
        (
            "Convert the query point to 16x16-tile coordinates, combine Y with "
            "the map width through BIOS MA_MUL8U, address the bit-packed "
            "collision bitmap at $275E/$275F, and return the selected bit in carry."
        ),
    ),
    MovementRegion(
        "collision_gate",
        0x5409,
        bytes.fromhex(
            "AD 60 27 85 1C AD 61 27 85 1D A5 1C 38 E9 08 85 1C "
            "B0 02 C6 1D AD 62 27 85 1E AD 63 27 85 1F A5 1E "
            "38 E9 10 85 1E B0 02 C6 1F AD 67 27 85 20 "
            "AD 68 27 85 21 20 0A 49 B0 26"
        ),
        (
            "Probe the collision bitmap from the player's offset footprint and "
            "branch on carry before any movement step is committed."
        ),
    ),
    MovementRegion(
        "animation_interpreter",
        0x451B,
        bytes.fromhex(
            "C6 21 D0 05 20 3B 45 80 13 C6 22 A5 22 1A D0 02 C6 23 "
            "B2 22 85 20 E6 22 D0 02 E6 23 20 7C 45 60 "
            "B2 22 C9 FF F0 05 20 4A 45 80 03 20 5F 45 60 "
            "B2 22 85 21 E6 22 D0 02 E6 23 B2 22 85 20 E6 22 D0 02 E6 23 60 "
            "E6 22 D0 02 E6 23 B2 22 48 E6 22 D0 02 E6 23 "
            "B2 22 48 68 85 23 68 85 22 20 4A 45 60"
        ),
        (
            "Run animation scripts as duration/frame pairs; FF followed by a "
            "16-bit pointer redirects the script, providing the loop primitive."
        ),
    ),
    MovementRegion(
        "direction_animation_scripts",
        0x4649,
        bytes.fromhex(
            "06 18 06 19 06 1A 06 1B FF 49 46 "
            "06 14 06 15 06 16 06 17 FF 54 46 "
            "06 1C 06 1D 06 1E 06 1F FF 5F 46 "
            "06 20 06 21 06 22 06 23 FF 6A 46 "
            "00 24 FF 75 46 00 25 FF 7A 46 "
            "00 26 FF 7F 46 00 27 FF 84 46"
        ),
        (
            "Four looping walk scripts and four looping one-frame idle/facing "
            "scripts selected by direction codes 1..4."
        ),
    ),
    MovementRegion(
        "collision_rectangle_registry",
        0x470C,
        bytes.fromhex(
            "9C 5D 26 60 A5 24 48 AD 5D 26 85 24 20 25 47 "
            "68 85 24 AD 5D 26 EE 5D 26 60 A5 24 0A 0A 0A A8 "
            "A5 1C 99 5E 26 C8 A5 1D 99 5E 26 C8 "
            "A5 1E 99 5E 26 C8 A5 1F 99 5E 26 C8 "
            "A5 20 99 5E 26 C8 A5 21 99 5E 26 C8 "
            "A5 22 99 5E 26 C8 A5 23 99 5E 26 60"
        ),
        (
            "Maintain a counted $265E array of 8-byte rectangles; each entry "
            "stores four two-byte bounds/coordinates."
        ),
    ),
    MovementRegion(
        "interaction_record_search",
        0x4B20,
        bytes.fromhex(
            "A5 1C 48 A5 1D 48 A5 1E 48 A5 1F 48 A5 20 48 A5 21 48 "
            "A5 22 48 A5 23 48 A5 24 48 A5 25 48 AD 79 27 85 24 "
            "AD 7A 27 85 25 82 8A 20 9B 4B A8 E8 B1 24 C8 C9 FF "
            "F0 17 CD 7B 27 D0 EE DA 20 AF 4B 20 86 51 FA 90 E4 "
            "A9 FF 8D 49 26 20 D8 4B 68 85 25 68 85 24 68 85 23 "
            "68 85 22 68 85 21 68 85 20 68 85 1F 68 85 1E "
            "68 85 1D 68 85 1C 60 "
            "85 1D 0A 85 1C 0A 0A 0A 18 65 1C 18 65 1D 60 "
            "0A 85 1C 0A 0A 0A 18 65 1C 60 "
            "85 1C 0A 0A 0A 0A 18 65 1C 60 "
            "B1 24 85 1C C8 B1 24 85 1D C8 B1 24 85 1E C8 "
            "B1 24 85 1F C8 B1 24 85 20 C8 B1 24 85 21 C8 "
            "B1 24 85 22 C8 B1 24 85 23 C8 60 "
            "82 B1 24 9D 03 37 C8 E8 E0 09 D0 F5 60"
        ),
        (
            "Scan 18-byte interaction records from the pointer in $2779/$277A: "
            "one class byte, eight bound bytes, and nine payload bytes. A matching "
            "class plus player-in-bounds test copies the payload to $3703-$370B."
        ),
    ),
    MovementRegion(
        "player_inside_interaction_bounds",
        0x5186,
        bytes.fromhex(
            "AD 60 27 C5 1C 90 2F AD 61 27 C5 1D 90 28 "
            "A5 20 CD 60 27 90 21 A5 21 CD 61 27 90 1A "
            "AD 62 27 C5 1E 90 13 AD 63 27 C5 1F 90 0C "
            "A5 22 CD 62 27 90 05 A5 23 CD 63 27 60"
        ),
        (
            "Test the player X/Y pairs against the eight bound bytes loaded "
            "from the selected interaction record; carry is the in-bounds result."
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
            "animation_countdown": "$2764",
            "animation_script_pointer": "$2765/$2766",
            "collision_bitmap_base": "$275E/$275F",
            "map_width_tiles": "$264A",
            "collision_rectangle_count": "$265D",
            "collision_rectangle_base": "$265E",
            "interaction_table_pointer": "$2779/$277A",
            "interaction_class": "$277B",
            "interaction_result_payload": "$3703-$370B",
        },
        "animation": {
            "walk_scripts": {str(key): f"0x{value:04X}" for key, value in WALK_ANIMATION_SCRIPTS.items()},
            "idle_scripts": {str(key): f"0x{value:04X}" for key, value in IDLE_ANIMATION_SCRIPTS.items()},
            "script_format": "duration, frame; FF lo hi redirects/loops",
        },
        "collision": {
            "tile_size_pixels": 16,
            "storage": "one bit per map tile",
            "row_width_tiles_address": "$264A",
            "bitmap_base_address": "$275E/$275F",
            "lookup": "byte_index=(tile_y*map_width_tiles+tile_x)//8; bit=tile_x&7",
            "rectangle_bytes": COLLISION_RECT_BYTES,
        },
        "interaction_records": {
            "record_bytes": INTERACTION_RECORD_BYTES,
            "class_bytes": 1,
            "bounds_bytes": INTERACTION_BOUNDS_BYTES,
            "payload_bytes": INTERACTION_PAYLOAD_BYTES,
            "terminator": "0xFF in class byte",
            "payload_destination": "$3703-$370B",
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
                "static code proves a bit-packed 16x16-tile collision bitmap and "
                "a separate 8-byte rectangle registry; live scene capture is still "
                "needed to assign game-facing meanings to individual bits/rectangles"
            ),
            "interaction_payload_semantics": (
                "record geometry and payload copying are proven; the nine payload "
                "bytes are preserved as opaque until their consumers are fully mapped"
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
