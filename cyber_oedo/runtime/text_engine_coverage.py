"""Game-wide text-engine coverage and non-dialogue text-family proof.

This module complements the shared dialogue architecture proof.  It classifies
text that does not enter through the common 27 28 dialogue stream, source-guards
the known fixed families, and documents the separate ENDING presentation
interpreter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.build.profiles.dossiers import OPENING_PROFILE_FIELDS
from cyber_oedo.build.profiles.media_mix import INFORMATION_SCREEN_LINES
from cyber_oedo.build.profiles.startup import (
    BOOT_MENU_PATCHES,
    MISSION_TITLE_PATCHES,
    STARTUP_V2_EXTRA_PATCHES,
)
from cyber_oedo.disc.game_layout import bank_for_offset
from cyber_oedo.graphics.title_screen import (
    TITLE_ASSET_BYTES,
    TITLE_SCREEN_SOURCE_SHA256,
)
from cyber_oedo.io import sha256_file
from cyber_oedo.resources import build_candidate_regions, discover_resource_headers
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256


@dataclass(frozen=True, slots=True)
class GuardedTextRegion:
    name: str
    offset: int
    length: int
    sha256: str
    purpose: str


DYNAMIC_LABEL_SOURCE = GuardedTextRegion(
    "dynamic_label_source",
    0x0013B800,
    769,
    "385fe67174f28f54787e9372b5ef865a34ab7f040ed46affd95c425f35d54576",
    "24 x 32-byte dynamic name/place/item records plus one trailing byte.",
)
COMMON_UI_TABLE = GuardedTextRegion(
    "common_command_system_ui",
    0x0013D800,
    0x250,
    "b8f6ba3027e1d6243f1030f29b8d08a8e253bd9ac12a7dd8f3457f70f0a3dde5",
    "37 fixed 16-byte command/system UI entries in the common text overlay.",
)
ENDING_OEDONET_STREAM = GuardedTextRegion(
    "ending_oedonet_stream",
    0x0500A800,
    0x43F,
    "2a4b1fb979fff5e867e911bd55b4aa7fa0935b1df8d3f963d229d8e6977f601e",
    "ENDING OEDONET/news command stream through the first 32-byte zero tail.",
)
ENDING_COMPLETION_STREAM = GuardedTextRegion(
    "ending_completion_save_credits_stream",
    0x0500D688,
    0x185,
    "550a0b7e53835cbefae49316a47792b6d77d026d833a47b03826aa543af89a7e",
    "Mission-complete/save/credits command stream including its FF terminator.",
)
ENDING_PRESENTATION_PARSER = GuardedTextRegion(
    "ending_presentation_parser",
    0x0500E493,
    0x2F5,
    "9d4d4329a4161eb9be582773788b85b8338504fca10418f66d87aea37a654c72",
    "ENDING mixed Shift-JIS/ASCII presentation interpreter.",
)

FIXED_REGIONS = (
    DYNAMIC_LABEL_SOURCE,
    COMMON_UI_TABLE,
    ENDING_OEDONET_STREAM,
    ENDING_COMPLETION_STREAM,
    ENDING_PRESENTATION_PARSER,
)

# M0-B through M8 share this exact table.  The early M0-A overlay is a
# different startup-era copy and is reported separately rather than silently
# folded into the common UI family.
COMMON_UI_OVERLAY_BASES = (
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
COMMON_UI_RELATIVE_OFFSET = 0xC000
COMMON_UI_BYTES = 0x250

RESOURCE_TEXT_FAMILIES = frozenset(
    {
        "INVENTRY",
        "DEN_EREV",
        "EREV",
        "INTER",
        "KANSHIKI",
        "KIDOU",
        "SHIRYO",
        "H_JYOUHO",
    }
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_fixed_regions(payload: bytes) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for region in FIXED_REGIONS:
        actual = payload[region.offset : region.offset + region.length]
        digest = _digest(actual)
        rows.append(
            {
                "name": region.name,
                "offset": f"0x{region.offset:08X}",
                "length": region.length,
                "sha256": digest,
                "matched": len(actual) == region.length and digest == region.sha256,
                "purpose": region.purpose,
            }
        )
    return tuple(rows)


def decode_fixed_ui_table(data: bytes) -> tuple[dict[str, Any], ...]:
    """Decode fixed 16-byte UI entries without assigning metadata semantics."""

    if len(data) % 16:
        raise ValueError("UI table length must be a multiple of 16")
    entries: list[dict[str, Any]] = []
    for index in range(len(data) // 16):
        raw = data[index * 16 : (index + 1) * 16]
        end = raw.find(b"\x00")
        if end < 0:
            raise ValueError(f"UI entry {index} lacks a null terminator")
        text_bytes = raw[:end]
        try:
            label = text_bytes.decode("shift_jis")
        except UnicodeDecodeError as error:
            raise ValueError(f"UI entry {index} has invalid Shift-JIS") from error
        entries.append(
            {
                "index": index,
                "label": label,
                "text_bytes": len(text_bytes),
                "metadata_hex": raw[end + 1 :].hex(),
            }
        )
    return tuple(entries)


def validate_ui_overlay_copies(
    payload: bytes,
    canonical: bytes,
) -> tuple[dict[str, Any], ...]:
    results: list[dict[str, Any]] = []
    for base in COMMON_UI_OVERLAY_BASES:
        start = base + COMMON_UI_RELATIVE_OFFSET
        actual = payload[start : start + COMMON_UI_BYTES]
        results.append(
            {
                "module_base": f"0x{base:08X}",
                "bank": bank_for_offset(base),
                "offset": f"0x{start:08X}",
                "sha256": _digest(actual),
                "matches_canonical": actual == canonical,
            }
        )
    return tuple(results)


def decode_dynamic_label_records(data: bytes) -> tuple[dict[str, Any], ...]:
    """Decode the two text slots in each 32-byte dynamic label record."""

    if len(data) != 769:
        raise ValueError("dynamic label source must be exactly 769 bytes")
    records: list[dict[str, Any]] = []
    for index in range(24):
        raw = data[index * 32 : (index + 1) * 32]
        slots: list[str] = []
        for start, limit in ((0, 13), (13, 26)):
            field = raw[start:limit]
            end = field.find(b"\x00")
            if end < 0:
                raise ValueError(f"dynamic label record {index + 1} lacks terminator")
            try:
                slots.append(field[:end].decode("shift_jis"))
            except UnicodeDecodeError as error:
                raise ValueError(
                    f"dynamic label record {index + 1} has invalid Shift-JIS"
                ) from error
        records.append(
            {
                "record": index + 1,
                "primary": slots[0],
                "alternate": slots[1],
                "state_hex": raw[26:32].hex(),
            }
        )
    return tuple(records)


def validate_profile_text(payload: bytes) -> dict[str, Any]:
    """Validate source bytes for existing startup, Media Mix, and dossier models."""

    startup = BOOT_MENU_PATCHES + STARTUP_V2_EXTRA_PATCHES + MISSION_TITLE_PATCHES
    startup_failures: list[str] = []
    for patch in startup:
        expected = patch.source_text.encode("shift_jis")
        if payload[patch.offset : patch.offset + len(expected)] != expected:
            startup_failures.append(patch.purpose)

    media_failures: list[str] = []
    for line in INFORMATION_SCREEN_LINES:
        command = bytes((0, 1, line.source_row))
        if payload[line.command_offset : line.command_offset + 3] != command:
            media_failures.append(f"{line.purpose} command")
        expected = line.source_text.encode("shift_jis") + b"\x00"
        if payload[line.text_offset : line.text_offset + len(expected)] != expected:
            media_failures.append(f"{line.purpose} text")

    dossier_failures: list[str] = []
    for field in OPENING_PROFILE_FIELDS:
        for copy_index, offset in enumerate(field.offsets):
            command = bytes((0, 12, field.source_row))
            if payload[offset - 3 : offset] != command:
                dossier_failures.append(
                    f"{field.profile} {field.purpose} copy {copy_index + 1} command"
                )
            expected = field.source_for_copy(copy_index).encode("shift_jis") + b"\x00"
            if payload[offset : offset + len(expected)] != expected:
                dossier_failures.append(
                    f"{field.profile} {field.purpose} copy {copy_index + 1} text"
                )

    return {
        "startup_system_and_mission_titles": {
            "records": len(startup),
            "matched": not startup_failures,
            "failures": startup_failures,
        },
        "media_mix_row_text": {
            "records": len(INFORMATION_SCREEN_LINES),
            "matched": not media_failures,
            "failures": media_failures,
        },
        "opening_dossiers": {
            "fields": len(OPENING_PROFILE_FIELDS),
            "copies": len(OPENING_PROFILE_FIELDS) * 2,
            "matched": not dossier_failures,
            "failures": dossier_failures,
        },
    }


def decode_ending_completion_stream(data: bytes) -> tuple[dict[str, Any], ...]:
    """Decode the proven ENDING opcodes 0/1/2 until the FF terminator."""

    rows: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(data):
        opcode = data[cursor]
        if opcode == 0xFF:
            if cursor != len(data) - 1:
                raise ValueError("ENDING stream has bytes after FF terminator")
            return tuple(rows)
        if opcode not in (0, 1, 2):
            raise ValueError(f"unsupported ENDING text opcode 0x{opcode:02X}")
        if cursor + 3 > len(data):
            raise ValueError("truncated ENDING text record")
        x_or_mode = data[cursor + 1]
        row = data[cursor + 2]
        end = data.find(b"\x00", cursor + 3)
        if end < 0:
            raise ValueError("unterminated ENDING text record")
        raw = data[cursor + 3 : end]
        encoding = "ascii" if opcode == 2 else "shift_jis"
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as error:
            raise ValueError("ENDING record failed its declared text encoding") from error
        rows.append(
            {
                "opcode": opcode,
                "x_or_mode": x_or_mode,
                "row": row,
                "encoding": encoding,
                "text": text,
            }
        )
        cursor = end + 1
    raise ValueError("ENDING stream lacks FF terminator")


def resource_family_instances(payload: bytes) -> dict[str, list[dict[str, Any]]]:
    headers = discover_resource_headers(payload)
    regions = build_candidate_regions(headers, len(payload) // 2048)
    grouped = {name: [] for name in sorted(RESOURCE_TEXT_FAMILIES)}
    for region in regions:
        name = region.header.name
        if name not in RESOURCE_TEXT_FAMILIES:
            continue
        raw = payload[region.start_offset : region.end_offset]
        grouped[name].append(
            {
                "bank": bank_for_offset(region.start_offset),
                "offset": f"0x{region.start_offset:08X}",
                "bytes": region.byte_count,
                "sha256": _digest(raw),
            }
        )
    return grouped


def build_text_engine_coverage_report(path: pathlib.Path) -> dict[str, Any]:
    payload = path.read_bytes()
    digest = sha256_file(path)
    fixed = validate_fixed_regions(payload)
    ui_data = payload[COMMON_UI_TABLE.offset : COMMON_UI_TABLE.offset + COMMON_UI_TABLE.length]
    labels_data = payload[
        DYNAMIC_LABEL_SOURCE.offset :
        DYNAMIC_LABEL_SOURCE.offset + DYNAMIC_LABEL_SOURCE.length
    ]
    ending_data = payload[
        ENDING_COMPLETION_STREAM.offset :
        ENDING_COMPLETION_STREAM.offset + ENDING_COMPLETION_STREAM.length
    ]

    profile_validation = validate_profile_text(payload)
    title_bytes = payload[40960 : 40960 + TITLE_ASSET_BYTES]

    families = (
        {
            "name": "shared_dialogue_bytecode",
            "banks": "MISSION_0 through MISSION_8",
            "storage": "27 28 marker + mixed Shift-JIS/control bytecode + 00",
            "renderer": "shared relocation-equivalent parser and byte-identical stock renderer",
            "status": "source-guarded elsewhere by prove-game-architecture",
        },
        {
            "name": "dynamic_names_places_items",
            "banks": "common M0-M8 text-overlay family",
            "storage": "24 x 32-byte indexed records, two 13-byte text slots plus state",
            "renderer": "dialogue opcode 3D -> stock renderer",
            "status": "source-guarded",
        },
        {
            "name": "command_system_ui",
            "banks": "M0-B and M1-M8 common overlays",
            "storage": "37 x 16-byte fixed Shift-JIS entries with per-entry metadata",
            "renderer": "overlay-local UI path using stock text assets",
            "status": "source-guarded and cross-copy matched",
        },
        {
            "name": "startup_save_memory_ui",
            "banks": "startup/boot",
            "storage": "fixed null-terminated fullwidth Shift-JIS strings",
            "renderer": "startup UI",
            "status": "source-guarded by build profile",
        },
        {
            "name": "mission_titles",
            "banks": "M1-M8 plus duplicate title resources",
            "storage": "fixed fullwidth Shift-JIS strings",
            "renderer": "mission-title presentation",
            "status": "source-guarded by build profile",
        },
        {
            "name": "opening_dossiers",
            "banks": "opening, two copies",
            "storage": "00 0C row + null-terminated Shift-JIS",
            "renderer": "row-addressed dossier interpreter",
            "status": "source-guarded by build profile",
        },
        {
            "name": "media_mix_information",
            "banks": "startup/media information",
            "storage": "00 01 row + null-terminated Shift-JIS plus formatting commands",
            "renderer": "row-addressed information-screen interpreter",
            "status": "source-guarded by build profile",
        },
        {
            "name": "resource_local_ui_labels",
            "banks": "mission-specific resources",
            "storage": "fixed tables inside INVENTRY/DEN_EREV/EREV/INTER/KANSHIKI/KIDOU/SHIRYO/H_JYOUHO",
            "renderer": "resource-specific UI paths",
            "status": "resource boundaries and complete source digests reported",
        },
        {
            "name": "ending_oedonet",
            "banks": "ENDING",
            "storage": "row-addressed Shift-JIS command stream with additional formatting commands",
            "renderer": "ENDING-specific news/information interpreter",
            "status": "source-guarded; command language partially decoded",
        },
        {
            "name": "ending_completion_save",
            "banks": "ENDING",
            "storage": "opcodes 0/1 + position bytes + null-terminated Shift-JIS",
            "renderer": "ENDING-specific mixed presentation interpreter",
            "status": "source-guarded and record format decoded",
        },
        {
            "name": "ending_credits",
            "banks": "ENDING",
            "storage": "opcode 2 + position bytes + null-terminated fixed-width ASCII",
            "renderer": "ENDING-specific ASCII credit path",
            "status": "source-guarded and record format decoded",
        },
        {
            "name": "opening_title_graphic",
            "banks": "startup/boot",
            "storage": "256x240, 960 consecutive 8x8 4bpp tiles",
            "renderer": "graphics/tile presentation, not a text parser",
            "status": "graphics-backed and source-hash guarded",
        },
    )

    return {
        "scope": "game-wide text-engine and non-dialogue text-family coverage",
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "fixed_regions": fixed,
        "profile_validation": profile_validation,
        "common_ui": {
            "entries": decode_fixed_ui_table(ui_data),
            "copies": validate_ui_overlay_copies(payload, ui_data),
        },
        "dynamic_labels": decode_dynamic_label_records(labels_data),
        "ending": {
            "common_dialogue_overlay_present": False,
            "completion_records": decode_ending_completion_stream(ending_data),
            "completion_stream_terminator": "0xFF",
            "opcode_formats": {
                "0": "two position/control bytes + null-terminated Shift-JIS; generic ending text path",
                "1": "two position/control bytes + null-terminated Shift-JIS; ending EX_GETFNT path",
                "2": "two position/control bytes + null-terminated ASCII; credits path",
            },
        },
        "resource_text_families": resource_family_instances(payload),
        "graphics_backed": {
            "opening_title_offset": "0x0000A000",
            "opening_title_bytes": TITLE_ASSET_BYTES,
            "opening_title_sha256": _digest(title_bytes),
            "opening_title_source_hash_matches": _digest(title_bytes)
            == TITLE_SCREEN_SOURCE_SHA256,
        },
        "families": families,
        "limits": {
            "ending_oedonet_commands": (
                "text-bearing row records and source extent are proven; not every "
                "non-text formatting opcode has a game-facing semantic name"
            ),
            "resource_local_renderers": (
                "resource boundaries/text tables are covered here; individual "
                "mission-specific UI caller semantics can still be expanded"
            ),
            "graphics_backed": (
                "the opening title is proven graphics-backed; other candidate "
                "tile graphics must be classified from actual graphic resources, "
                "not assumed from screenshots"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate game-wide text families outside the common dialogue stream."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_text_engine_coverage_report(args.payload)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    fixed_ok = all(item["matched"] for item in report["fixed_regions"])
    profiles_ok = all(
        item["matched"] for item in report["profile_validation"].values()
    )
    ui_ok = all(item["matches_canonical"] for item in report["common_ui"]["copies"])
    return 0 if (
        report["payload_authenticated"]
        and fixed_ok
        and profiles_ok
        and ui_ok
        and report["graphics_backed"]["opening_title_source_hash_matches"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
