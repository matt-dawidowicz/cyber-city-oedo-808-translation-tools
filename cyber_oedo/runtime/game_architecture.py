"""Game-wide source-backed architecture evidence.

This module joins the separately proven movement, collision, interaction, scene
loading, and text-rendering paths.  It intentionally distinguishes byte-identical
shared machinery from relocated copies and from scene-specific data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.movement import MOVEMENT_MODULE_PAYLOAD_BASE


@dataclass(frozen=True, slots=True)
class HashedRegion:
    name: str
    module_base: int
    cpu_start: int
    length: int
    sha256: str
    purpose: str

    @property
    def payload_offset(self) -> int:
        return self.module_base + self.cpu_start


MOVEMENT_ARCHITECTURE_REGIONS = (
    HashedRegion(
        "exploration_loop_and_transition_return",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x4000,
        0x52,
        "a52bdf79a7084ee15da909d5af23b0ebc8ee563649898b94325d6d9a145408e4",
        "Run exploration, stop on $2649, and promote FF transition payload bytes $3704-$3706 to $3700-$3702.",
    ),
    HashedRegion(
        "scene_and_room_setup",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x40E9,
        0x152,
        "00cf5bd95522ce8544b806c4906bbbc2664efb3760e29cf57b8cfbacf0db2101",
        "Select scene and room descriptors, install collision/entity/interaction pointers, and optionally restore room spawn X/Y.",
    ),
    HashedRegion(
        "scene_cd_loaders",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x423B,
        0x53,
        "db36a3780ed8bfa35ef602dc2fcf3e451211a7f4401807efefd43a1a7862d825",
        "Translate scene descriptor bytes into System Card CD_READ argument blocks.",
    ),
    HashedRegion(
        "camera_poststep_bridge",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x4ADB,
        0x30,
        "4a7672729286508239fb6d3f74e0aef84a73ea9d3acb9a8e9d89387693289ffc",
        "Copy the committed player X/Y to the camera update path after every unit movement step.",
    ),
    HashedRegion(
        "camera_center_and_clamp",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x43F6,
        0x121,
        "07c59a15b52e0aa75b749a4cb7506da3a9bd7d4a5578bd9dfbb64083511f74b8",
        "Derive clamped camera origins from player X/Y and dispatch signed X/Y scroll deltas.",
    ),
    HashedRegion(
        "pixel_scroll_dispatch",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x5EB2,
        0x7C,
        "c0320d74b6f385e4c109774861836ac90a2ef196d71855190368a2e4c1b0d33c",
        "Consume signed camera deltas one pixel at a time.",
    ),
    HashedRegion(
        "pixel_scroll_steps",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x5F2E,
        0xFE,
        "956dc3faf3dfe5aafbe1b302cb6b080fc421f15345282a8ec76b668b5a26350c",
        "Update $220C/$2210 and advance tile origins exactly on 16-pixel crossings.",
    ),
    HashedRegion(
        "tile_refill",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x602C,
        0xF9,
        "cebced19be9df0d98d7b723b6ac14842a7619f34f3aa33e3d8b3ad5976b65bb0",
        "Refill newly exposed map columns/rows after camera tile-origin changes.",
    ),
    HashedRegion(
        "interaction_button_dispatch",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x4B0B,
        0x15,
        "5c22da985233929909152df301d38412a11532e9c9c7d6d240616563bde22bc2",
        "Route normalized Button II separately and Button I to interaction class 1.",
    ),
    HashedRegion(
        "interaction_record_scan",
        MOVEMENT_MODULE_PAYLOAD_BASE,
        0x4B20,
        0xC5,
        "99521c8ccdc50ee65c4d798db6e36a9da27bc8df4fb922d9730d05f72d381f6f",
        "Select the first matching 18-byte interaction record whose class and player bounds match.",
    ),
)

MISSION0_TEXT_BASE = 0x00131800
TEXT_ARCHITECTURE_REGIONS = (
    HashedRegion(
        "dialogue_control_dispatch",
        MISSION0_TEXT_BASE,
        0x9543,
        0xAA,
        "8b6c60a173095cc026f51e5177b7a1f5383ca3438028c8bc4b3d92d18d57aa00",
        "Shared dialogue bytecode dispatcher for 40, 2A, 2F, 5C, 7E, 3D, 21, terminator, and ordinary Shift-JIS pairs.",
    ),
    HashedRegion(
        "dialogue_waits",
        MISSION0_TEXT_BASE,
        0x95ED,
        0x22,
        "ff4c44b0de5851c493760819c4c1523aee3965c2a3bb2de8505e3c5fe897d9ce",
        "Skippable 20-vsync wait and press-then-release wait.",
    ),
    HashedRegion(
        "cursor_and_wrap",
        MISSION0_TEXT_BASE,
        0x58CE,
        0x47,
        "106d5c09e06c7952fe00206d46820ba5208586e1c1f834fc52f41faecd8dba80",
        "Reset column, advance row, scroll at row 3, and render null-terminated glyph-pair strings.",
    ),
    HashedRegion(
        "text_cell_grid_write",
        MISSION0_TEXT_BASE,
        0x59B7,
        0xBC,
        "1722d35d4b3407b030ec845ccfd5946eb6fcf06c11595c196f9a3c331f726845",
        "Address and update the 3-row x 12-cell x 3-byte text grid and apply glyph pacing.",
    ),
    HashedRegion(
        "text_redraw_scroll_init",
        MISSION0_TEXT_BASE,
        0x5A73,
        0xA7,
        "442035130aa48f8ba165885b9c41c83e185d627cd48a2f97e5211e8022b163c0",
        "Redraw all 36 cells, scroll 24 cells upward, blank the last row, and initialize cursor state.",
    ),
    HashedRegion(
        "dialogue_vram_bases",
        MISSION0_TEXT_BASE,
        0x5444,
        0x47,
        "c546d838a61d818eba27bed3c880bd3d2258367c6167c27142fbdc75efef953f",
        "Install dialogue BAT base $7900 and glyph-pattern VRAM base $6D00.",
    ),
)

TEXT_OVERLAY_BASES = (
    0x00074800,
    0x00131800,
    0x00CE4000,
    0x017B3800,
    0x0222C000,
    0x02B1C000,
    0x03356800,
    0x03B34000,
    0x04281800,
    0x04848000,
)
TEXT_PARSER_ENTRIES = (
    0x94A7,
    0x9543,
    0x95AA,
    0x95AE,
    0x9580,
    0x950E,
    0x9581,
    0x9526,
    0x94A8,
    0x94A7,
)
EXPLORATION_WRAPPER_BASES = (
    0x00054800,
    0x00A40000,
    0x01553800,
    0x02015000,
    0x0289E000,
    0x0314D800,
    0x0390B000,
    0x03FDF800,
    0x04652000,
    0x04CC5800,
)

RENDERER_SIGNATURE = bytes.fromhex(
    "A5 00 48 A5 01 48 20 46 59 85 31 A5 30 C5 31"
)
MOVEMENT_SIGNATURE = bytes.fromhex(
    "AD 28 22 82 0A B0 07 E8 E0 08 D0 F8 62 60"
)
EXPLORATION_WRAPPER_SIGNATURE = bytes.fromhex(
    "AD 00 37 C9 FF D0 02 A0 01 A2 01 60"
)
PARSER_ANCHOR = bytes.fromhex("A8 D0 01 60 C9 40")
PARSER_CONTROL_OFFSETS = {
    0x0A: 0x40,
    0x16: 0x2A,
    0x28: 0x2F,
    0x31: 0x5C,
    0x3A: 0x7E,
    0x4C: 0x3D,
    0x7C: 0x21,
    0x91: 0x80,
}
PARSER_RELOC_WORD_OFFSETS = (
    0x01, 0x04, 0x0F, 0x1B, 0x1E, 0x2D, 0x36, 0x3F, 0x42, 0x51,
    0x54, 0x57, 0x5A, 0x5D, 0x62, 0x78, 0x87, 0x8F, 0x9A, 0x9D,
)

CONTROL_SEMANTICS = {
    "00": "terminate current dialogue stream",
    "40": "explicit line advance; scroll when advancing into row 3",
    "2A": "consume one ASCII-like digit operand and set glyph delay $2827 to operand-$30",
    "2F": "wait up to 20 vsyncs, shortened while low joy bits are held",
    "5C": "wait for a controller press and then full release",
    "7E": "consume one ASCII-like digit operand and set per-cell attribute $2763 to operand-$30",
    "3D": "consume two operands; use operand 1 to select one $A400 32-byte record and render its active text field",
    "21": "wait until trigger bits $222D&3 are set or asynchronous state $37F1 becomes nonzero",
    ">80": "ordinary two-byte Shift-JIS glyph pair rendered through $5915",
    "<=80 other": "ignored by this dispatcher",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _find_all(data: bytes, pattern: bytes) -> tuple[int, ...]:
    hits: list[int] = []
    start = 0
    while True:
        found = data.find(pattern, start)
        if found < 0:
            return tuple(hits)
        hits.append(found)
        start = found + 1


def validate_hashed_regions(
    payload: bytes,
    regions: tuple[HashedRegion, ...],
) -> tuple[dict[str, Any], ...]:
    results: list[dict[str, Any]] = []
    for region in regions:
        start = region.payload_offset
        actual = payload[start : start + region.length]
        digest = _sha256(actual)
        results.append(
            {
                "name": region.name,
                "cpu_start": f"0x{region.cpu_start:04X}",
                "payload_offset": f"0x{start:08X}",
                "length": region.length,
                "sha256": digest,
                "matched": len(actual) == region.length and digest == region.sha256,
                "purpose": region.purpose,
            }
        )
    return tuple(results)


def _parser_entry(payload: bytes, base: int) -> int | None:
    region_start = base + 0x9000
    region_end = min(base + 0xA000, len(payload))
    hit = payload.find(PARSER_ANCHOR, region_start, region_end)
    if hit < 0:
        return None
    return hit - base - 6


def _relocation_equivalent_parsers(payload: bytes) -> tuple[dict[str, Any], ...]:
    canonical_entry = TEXT_PARSER_ENTRIES[1]
    canonical = payload[
        MISSION0_TEXT_BASE + canonical_entry :
        MISSION0_TEXT_BASE + canonical_entry + 0xA0
    ]
    results: list[dict[str, Any]] = []
    address_bytes = {
        byte
        for offset in PARSER_RELOC_WORD_OFFSETS
        for byte in (offset, offset + 1)
    }
    for expected_base, expected_entry in zip(TEXT_OVERLAY_BASES, TEXT_PARSER_ENTRIES):
        entry = _parser_entry(payload, expected_base)
        blob = (
            payload[expected_base + entry : expected_base + entry + 0xA0]
            if entry is not None
            else b""
        )
        delta = None if entry is None else entry - canonical_entry
        non_address_equal = (
            len(blob) == len(canonical)
            and all(
                blob[index] == canonical[index]
                for index in range(len(canonical))
                if index not in address_bytes
            )
        )
        relocated_words_equal = len(blob) == len(canonical) and delta is not None
        if relocated_words_equal:
            for offset in PARSER_RELOC_WORD_OFFSETS:
                expected_word = (
                    int.from_bytes(canonical[offset : offset + 2], "little") + delta
                ) & 0xFFFF
                actual_word = int.from_bytes(blob[offset : offset + 2], "little")
                if actual_word != expected_word:
                    relocated_words_equal = False
                    break
        controls_match = len(blob) == len(canonical) and all(
            blob[offset] == 0xC9 and blob[offset + 1] == opcode
            for offset, opcode in PARSER_CONTROL_OFFSETS.items()
        )
        results.append(
            {
                "module_base": f"0x{expected_base:08X}",
                "parser_entry": None if entry is None else f"0x{entry:04X}",
                "expected_entry": f"0x{expected_entry:04X}",
                "entry_matched": entry == expected_entry,
                "relocation_delta_from_mission0": delta,
                "non_address_bytes_match": non_address_equal,
                "relocated_absolute_targets_match": relocated_words_equal,
                "control_dispatch_matches": controls_match,
            }
        )
    return tuple(results)


def build_game_architecture_report(path: pathlib.Path) -> dict[str, Any]:
    payload = path.read_bytes()
    movement_regions = validate_hashed_regions(payload, MOVEMENT_ARCHITECTURE_REGIONS)
    text_regions = validate_hashed_regions(payload, TEXT_ARCHITECTURE_REGIONS)

    renderer_hits = _find_all(payload, RENDERER_SIGNATURE)
    renderer_bases = tuple(hit - 0x5915 for hit in renderer_hits)
    movement_hits = _find_all(payload, MOVEMENT_SIGNATURE)
    wrapper_hits = _find_all(payload, EXPLORATION_WRAPPER_SIGNATURE)
    wrapper_bases = tuple(hit - 0x40D5 for hit in wrapper_hits)
    parsers = _relocation_equivalent_parsers(payload)

    return {
        "scope": "game-wide static architecture correlation",
        "payload_sha256": sha256_file(path),
        "payload_authenticated": sha256_file(path) == TRACK2_PAYLOAD_SHA256,
        "movement_regions": movement_regions,
        "text_regions": text_regions,
        "camera": {
            "player_position": "$2760-$2763",
            "desired_origin": (
                "clamp(player_axis - 128, 0, map_axis_pixels - 256)"
            ),
            "pixel_scroll_x": "$220C/$220D",
            "pixel_scroll_y": "$2210/$2211",
            "tile_origin_x": "$289C/$289D",
            "tile_origin_y": "$289E/$289F",
            "tile_refill_rule": (
                "pixel scroll changes every committed movement unit; map row/column "
                "refill occurs only when a low nibble crosses a 16-pixel boundary"
            ),
        },
        "interaction": {
            "button_i_normalized_code": 8,
            "button_i_class": 1,
            "automatic_trigger_class": 0,
            "selection_order": "first class-matching record whose bounds contain player X/Y",
            "facing_check_in_button_i_scan": False,
            "facing_note": (
                "the Button I scan does not read the facing/animation state; any "
                "'must face NPC' behavior is encoded by spatial record geometry or "
                "higher-level scene data rather than a direct facing predicate here"
            ),
            "successful_record_payload": "$3703-$370B",
        },
        "transitions": {
            "scene_selector": "$3700",
            "room_selector": "$3701",
            "resume_or_spawn_state": "$3702",
            "transition_payload": "$3703-$370B",
            "transition_sentinel": "$3703 == $FF",
            "promotion": "$3704->$3700, $3705->$3701, $3706->$3702",
            "room_descriptor": {
                "+0..+3": "initial player X/Y, used when $3702 == 0",
                "+4": "$264C scene flag",
                "+5..+6": "$277E/$277F entity-source pointer",
                "+7..+8": "$2779/$277A interaction-record pointer",
                "+9..+10": "CD/data descriptor pointer consumed by the room loader",
                "+11..+12": "self-modified loader source used by the room data transfer",
            },
            "cd_read_entry": "$E009",
        },
        "overlay_identity": {
            "movement_signature_hits": len(movement_hits),
            "movement_signature_offsets": [f"0x{hit:08X}" for hit in movement_hits],
            "movement_common_core_is_singleton": len(movement_hits) == 1,
            "renderer_signature_hits": len(renderer_hits),
            "renderer_module_bases": [f"0x{base:08X}" for base in renderer_bases],
            "expected_renderer_module_bases_match": renderer_bases == TEXT_OVERLAY_BASES,
            "exploration_wrapper_hits": len(wrapper_hits),
            "exploration_wrapper_bases": [f"0x{base:08X}" for base in wrapper_bases],
            "expected_exploration_wrapper_bases_match": wrapper_bases == EXPLORATION_WRAPPER_BASES,
            "parser_overlays": parsers,
            "all_parser_overlays_relocation_equivalent": all(
                item["entry_matched"]
                and item["non_address_bytes_match"]
                and item["relocated_absolute_targets_match"]
                and item["control_dispatch_matches"]
                for item in parsers
            ),
        },
        "text": {
            "cursor_column": "$30",
            "cursor_row": "$2F",
            "grid": "$26F3-$275E inclusive; 36 cells x 3 bytes",
            "grid_geometry": "3 rows x 12 cells",
            "cell_layout": "Shift-JIS high byte, low byte, attribute",
            "wrap_width": "11 ordinary cells; selected punctuation may use cell 12",
            "scroll": "row 1-2 copied over row 0-1; final 12 cells blanked",
            "bat_vram_base": "$7900",
            "glyph_pattern_vram_base": "$6D00",
            "renderer_paths_to_5915": {
                "$5903": "generic null-terminated two-byte glyph string",
                "parser ordinary glyph": "stream byte > $80 plus following byte",
                "$9626": "$3D indexed-record active-field renderer",
            },
            "direct_positioned_cell_renderer": "$5693",
            "controls": CONTROL_SEMANTICS,
        },
        "architecture_chain": [
            "disc scene/overlay descriptor",
            "CD_READ / resource installation",
            "scene + room descriptor pointers",
            "input normalization",
            "movement direction + collision bitmap / occupancy rectangles",
            "player coordinate commit",
            "camera clamp + pixel scroll",
            "16-pixel map row/column refill",
            "interaction record selection",
            "transition payload / command handoff",
            "script dialogue dispatch",
            "text grid + cursor/window state",
            "System Card font fetch",
            "glyph pattern VRAM + BAT write",
        ],
        "limits": {
            "proof_level": "static source-guarded and cross-copy correlated",
            "live_remaining": (
                "MPR captures are still required to assign runtime bank identity "
                "to representative scenes and to correlate scene-specific payload "
                "values with named rooms/NPCs."
            ),
            "interaction_payload": (
                "the 9-byte record payload is structurally proven, but bytes beyond "
                "the FF transition form remain semantically scene-dependent"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the game-wide Cyber City Oedo 808 architecture map."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_game_architecture_report(args.payload)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    ok = (
        report["payload_authenticated"]
        and all(item["matched"] for item in report["movement_regions"])
        and all(item["matched"] for item in report["text_regions"])
        and report["overlay_identity"]["movement_common_core_is_singleton"]
        and report["overlay_identity"]["expected_renderer_module_bases_match"]
        and report["overlay_identity"]["expected_exploration_wrapper_bases_match"]
        and report["overlay_identity"]["all_parser_overlays_relocation_equivalent"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
