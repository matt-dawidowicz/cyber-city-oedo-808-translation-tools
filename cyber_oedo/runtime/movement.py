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
SCENE_INDEX = 0x3700
SCENE_ENTRY_INDEX = 0x3701
SCENE_POSITION_MODE = 0x3702
STATIC_OBJECT_SOURCE_POINTER = 0x277E
STATIC_OBJECT_COUNT = 0x277D
LIVE_OBJECT_BASE = 0x2783
METASPRITE_TABLE_CPU = 0x5A37
CAMERA_SCROLL_X = 0x220C
CAMERA_SCROLL_Y = 0x2210

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
STATIC_OBJECT_SOURCE_BYTES = 8
LIVE_OBJECT_BYTES = 16
METASPRITE_COMPONENT_BYTES = 6

PLAYER_FRAME_COMPONENTS = {
    0x14: ((640, -16, -48, 4481), (648, -16, -16, 385)),
    0x15: ((672, -16, -48, 4481), (680, -16, -16, 385)),
    0x16: ((704, -16, -48, 4481), (712, -16, -16, 385)),
    0x17: ((736, -16, -48, 4481), (744, -16, -16, 385)),
    0x18: ((652, -16, -48, 385), (656, -16, -32, 4481)),
    0x19: ((684, -16, -48, 385), (688, -16, -32, 4481)),
    0x1A: ((716, -16, -48, 385), (720, -16, -32, 4481)),
    0x1B: ((748, -16, -48, 385), (752, -16, -32, 4481)),
    0x1C: ((664, -16, -48, 4481), (768, -16, -16, 385)),
    0x1D: ((800, -16, -16, 385), (696, -16, -48, 4481)),
    0x1E: ((728, -16, -48, 4481), (832, -16, -16, 385)),
    0x1F: ((864, -16, -16, 385), (760, -16, -48, 4481)),
    0x20: ((772, -16, -48, 385), (776, -16, -32, 4481)),
    0x21: ((804, -16, -48, 385), (808, -16, -32, 4481)),
    0x22: ((836, -16, -48, 385), (840, -16, -32, 4481)),
    0x23: ((868, -16, -48, 385), (872, -16, -32, 4481)),
    0x24: ((784, -16, -48, 4481), (792, -16, -16, 385)),
    0x25: ((816, -16, -48, 4481), (824, -16, -16, 385)),
    0x26: ((848, -16, -48, 4481), (856, -16, -16, 385)),
    0x27: ((880, -16, -32, 4481), (888, -16, 0, 385)),
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
    MovementRegion(
        "scene_result_promotion",
        0x402B,
        bytes.fromhex(
            "20 B1 40 A0 02 AD 03 37 C9 FF D0 03 20 3D 40 A2 01 60 "
            "AD 04 37 8D 00 37 AD 05 37 8D 01 37 AD 06 37 8D 02 37 "
            "A0 01 60"
        ),
        (
            "When interaction result byte $3703 is FF, promote $3704-$3706 "
            "into the active scene selector, entry selector, and position mode."
        ),
    ),
    MovementRegion(
        "scene_entry_selection",
        0x419E,
        bytes.fromhex(
            "AD 01 37 0A A8 AD 0A 70 85 2A AD 0B 70 85 2B "
            "B1 2A C8 85 28 B1 2A 85 29 AD 02 37 D0 18 C2 "
            "B1 28 8D 60 27 C8 B1 28 8D 61 27 C8 B1 28 8D 62 27 "
            "C8 B1 28 8D 63 27 A0 04 B1 28 8D 4C 26 C8 "
            "B1 28 8D 7E 27 C8 B1 28 8D 7F 27 C8 B1 28 8D 79 27 "
            "C8 B1 28 8D 7A 27 C8 B1 28 85 1E C8 B1 28 85 1F "
            "C8 B1 28 8D 1E 42 C8 B1 28 8D 1F 42"
        ),
        (
            "Use $3701 to select a scene-entry record. When $3702 is zero, "
            "load player X/Y from that record; always load object and interaction "
            "table pointers plus scene-local loader fields."
        ),
    ),
    MovementRegion(
        "camera_follow_bridge",
        0x4ADB,
        bytes.fromhex(
            "A5 1C 48 A5 1D 48 A5 1E 48 A5 1F 48 "
            "AD 60 27 85 1C AD 61 27 85 1D AD 62 27 85 1E "
            "AD 63 27 85 1F 20 F6 43 "
            "68 85 1F 68 85 1E 68 85 1D 68 85 1C 60"
        ),
        (
            "Feed the newly committed player X/Y position into the camera "
            "follow/clamp routine after every movement step."
        ),
    ),
    MovementRegion(
        "object_source_initialization",
        0x5519,
        bytes.fromhex(
            "9C 80 27 20 3B 55 AD 30 28 C9 FF F0 0E 20 88 55 20 7D 56 "
            "EE 80 27 20 40 56 80 E8 AD 80 27 8D 7D 27 60 "
            "A5 2A 48 A5 2B 48 AD 80 27 0A 0A 0A A8 AD 7E 27 85 2A "
            "AD 7F 27 85 2B B1 2A C8 8D 30 28 B1 2A C8 8D 31 28 "
            "B1 2A C8 8D 23 28 B1 2A C8 8D 24 28 B1 2A C8 8D 25 28 "
            "B1 2A C8 8D 26 28 B1 2A C8 8D 2E 28 B1 2A 8D 2F 28 "
            "68 85 2B 68 85 2A 60"
        ),
        (
            "Read 8-byte scene object source records from $277E/$277F until "
            "type FF, initialize runtime fields, and persist each as a 16-byte "
            "live object record."
        ),
    ),
    MovementRegion(
        "live_object_update",
        0x55E9,
        bytes.fromhex(
            "AD 7D 27 8D 80 27 AD 80 27 F0 0E 20 03 56 20 BE 56 "
            "20 40 56 CE 80 27 80 ED 60 "
            "AD 80 27 8D 39 56 9C 3A 56 CE 39 56 "
            "0E 39 56 2E 3A 56 0E 39 56 2E 3A 56 "
            "0E 39 56 2E 3A 56 0E 39 56 2E 3A 56 "
            "AD 39 56 18 69 83 8D 39 56 AD 3A 56 69 27 8D 3A 56 "
            "73 00 00 23 28 10 00 60"
        ),
        (
            "Iterate the $277D live-object count, address $2783 + index*16, "
            "copy each object to the scratch record, run animation, and write "
            "the updated 16-byte record back."
        ),
    ),
    MovementRegion(
        "metasprite_renderer",
        0x5769,
        bytes.fromhex(
            "AD 76 28 0A 0A 18 6D 76 28 A8 "
            "B9 35 28 8D 77 28 B9 36 28 8D 78 28 "
            "B9 37 28 8D 79 28 B9 38 28 8D 7A 28 "
            "B9 39 28 8D 7B 28 60 "
            "A5 1C 48 A9 37 85 00 A9 5A 85 01 62 CD 77 28 F0 18 "
            "48 B2 00 0A 85 1C 0A 18 65 1C 1A 18 65 00 85 00 "
            "90 02 E6 01 68 1A 80 E3 68 85 1C 60 "
            "B2 00 8D 82 28 A0 01 62 48 20 DB 57 5A 20 00 58 "
            "EE 83 28 7A 68 1A CD 82 28 D0 ED 60 "
            "B1 00 8D 80 28 C8 B1 00 8D 81 28 C8 "
            "B1 00 8D 7E 28 C8 B1 00 8D 7F 28 C8 "
            "B1 00 8D 7C 28 C8 B1 00 8D 7D 28 C8 60"
        ),
        (
            "Resolve a frame ID through the meta-sprite table at $5A37. Each "
            "frame starts with a component count; each six-byte component is "
            "pattern word, signed X offset, signed Y offset, attribute word."
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
            "scene_index": "$3700",
            "scene_entry_index": "$3701",
            "scene_position_mode": "$3702",
            "static_object_source_pointer": "$277E/$277F",
            "static_object_count": "$277D",
            "live_object_base": "$2783",
            "camera_scroll_x": "$220C/$220D",
            "camera_scroll_y": "$2210/$2211",
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
            "transition_header": (
                "$3703 == FF promotes $3704-$3706 to $3700-$3702"
            ),
        },
        "scene_transition": {
            "scene_selector": "$3700 selects a 9-byte CD/resource descriptor",
            "entry_selector": "$3701 selects a scene-entry pointer",
            "position_mode": (
                "$3702 == 0 reloads player X/Y from the entry record; nonzero "
                "preserves the established position"
            ),
        },
        "objects": {
            "source_record_bytes": STATIC_OBJECT_SOURCE_BYTES,
            "source_pointer": "$277E/$277F",
            "source_terminator": "0xFF in source record byte 0",
            "live_record_bytes": LIVE_OBJECT_BYTES,
            "live_base": "$2783",
            "live_count": "$277D",
            "source_fields": {
                "+0": "animation/type selector",
                "+1": "auxiliary byte, semantic name not yet proven",
                "+2/+3": "X position",
                "+4/+5": "Y position",
                "+6/+7": "auxiliary word, semantic name not yet proven",
            },
        },
        "metasprites": {
            "table_cpu": f"0x{METASPRITE_TABLE_CPU:04X}",
            "component_bytes": METASPRITE_COMPONENT_BYTES,
            "component_format": (
                "pattern_word, signed_x_offset, signed_y_offset, attribute_word"
            ),
            "player_frames": {
                f"0x{frame:02X}": components
                for frame, components in PLAYER_FRAME_COMPONENTS.items()
            },
        },
        "camera": {
            "follow_bridge": "$4ADB -> $43F6 after every coordinate commit",
            "scroll_x": "$220C/$220D",
            "scroll_y": "$2210/$2211",
            "tile_refill_boundary_pixels": 16,
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
                "the transition form is proven for bytes 0..3 when byte 0 is FF; "
                "other payload forms and bytes 4..8 remain opaque"
            ),
            "object_auxiliary_fields": (
                "source object bytes +1 and +6/+7 are preserved but not assigned "
                "game-facing names until their consumers are mapped"
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
