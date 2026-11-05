"""Completion proofs for information pages and named binary UI assets.

This module closes the remaining static text-engine gaps that are deliberately
kept separate from the common dialogue parser:

* the shared 0..10 information-page command language used by Media Mix,
  mission information pages, and ENDING/OEDONET;
* the fixed 16-byte name -> CD-resource descriptor tables in the common
  mission overlays;
* the common runtime resource lookup/load/cache path; and
* a conservative translation-ownership map that states which families may be
  edited in place and which remain relocation-gated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.disc.game_layout import bank_for_offset
from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import TRACK2_START_LBA
from cyber_oedo.graphics.title_screen import TITLE_ASSET_BYTES
from cyber_oedo.runtime.text_engine_coverage import ENDING_OEDONET_STREAM


INFORMATION_STREAM_HEADER = bytes.fromhex("02 01 05 01 06 00 00 50")
INFORMATION_PARSER_OFFSET = 0x05001DC7
INFORMATION_PARSER_LENGTH = 0x3A7
INFORMATION_PARSER_SHA256 = (
    "8127516e6f65c590c63ad2a7eecce08a3f7c2ef161d07cee8de328943e3cd47d"
)
INFORMATION_PARSER_COPY_OFFSETS = (
    0x0178CDC7,
    0x022055C7,
    0x02AF55C7,
    0x0332FDC7,
    0x03B0D5C7,
    0x0425ADC7,
    0x048215C7,
    0x05001DC7,
)
INFORMATION_VARIANT_DISPATCH_OFFSETS = (
    0x0000731D,
    0x000221E2,
    0x00061C60,
)

INFORMATION_FIXED_ARGUMENT_BYTES = {
    1: 1,
    2: 1,
    3: 0,
    4: 0,
    5: 1,
    6: 3,
    7: 5,
    8: 0,
    9: 0,
    10: 0,
}

INFORMATION_COMMAND_SEMANTICS = {
    0: "render null-terminated Shift-JIS at explicit X/Y coordinates",
    1: "set the glyph-pattern VRAM high-page/base selector",
    2: "set per-glyph delay counter $BF09",
    3: "terminate the information-page command stream",
    4: "toggle internal display phase $BF05 between $00 and $FF",
    5: "set periodic display-update interval $BF04 and arm countdown $BF06",
    6: (
        "set text X/Y state $BF0A/$BF0B and transiently load a third delay "
        "operand before restoring the previous $BF09 value"
    ),
    7: (
        "draw a sequential rectangular BAT/tile block; operands are "
        "mode, X, Y, width, height"
    ),
    8: (
        "wait for ADPCM idle, then issue a zeroed EX_SPRPUT/display-marker "
        "cleanup before continuing"
    ),
    9: "wait through vertical sync until held controller state $2228 is nonzero",
    10: "vertical-sync and run the information-screen display reset path",
}

RESOURCE_DESCRIPTOR_TABLES = (
    ("MISSION_0_A", 0x0007A58B),
    ("MISSION_0_B", 0x0013754B),
    ("MISSION_1", 0x00CE9D6B),
    ("MISSION_2", 0x017B956B),
    ("MISSION_3", 0x02231D6B),
    ("MISSION_4", 0x02B21D6B),
    ("MISSION_5", 0x0335C56B),
    ("MISSION_6", 0x03B39D6B),
    ("MISSION_7", 0x0428756B),
    ("MISSION_8", 0x0484DD8B),
)
RESOURCE_DESCRIPTOR_BYTES = 16
RESOURCE_NAME_BYTES = 10
RESOURCE_UI_ASSET_NAMES = frozenset(
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

M0B_RUNTIME_REGIONS = (
    (
        "resource_name_lookup",
        0x00138636,
        0x6A,
        "61bd6308f03c34d77155443c5601b280301c715b3821288c30589fd1c382e52a",
        (
            "Walk 16-byte descriptors from logical $5D4B, compare the "
            "requested 10-byte name, and install sector/span/length fields."
        ),
    ),
    (
        "resource_load_install",
        0x001384CB,
        0x170,
        "e510448be7ae09a7d24cda174cfc36a9a7efff5e5a020b8d832aaaa22f7710a1",
        (
            "Resolve a named resource, allocate/cache its destination, run the "
            "byte loader, and install/copy the loaded block."
        ),
    ),
    (
        "byte_loader",
        0x001386A0,
        0x50,
        "68de02bf0a681ceb49397362dd005806b6bd915d2b11c2e3b0b5d5618cd8b338",
        "Load full sectors plus a remainder through the common CD byte-loader.",
    ),
    (
        "dynamic_tii_copy",
        0x00135A0C,
        0x32,
        "ca8df51da341a148dc5cf545eaf76f235d198b302b93e806447b3bbbbec0b27e",
        (
            "Patch the source/destination/length operands of one TII and use "
            "it as the generic post-load memory copy primitive."
        ),
    ),
    (
        "resource_cache",
        0x0013A74A,
        0xB0,
        "e19c06d05956a6da71ad6b1b792da52f5c44531236312583909c9f0afc1922e2",
        (
            "Search the 16-slot resource cache at $34A9 and load/install a "
            "named resource only when it is not already resident."
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    table_label: str
    table_offset: int
    index: int
    name: str
    sector: int
    sector_span: int
    byte_length: int

    @property
    def record_offset(self) -> int:
        return self.table_offset + self.index * RESOURCE_DESCRIPTOR_BYTES

    @property
    def payload_offset(self) -> int:
        relative_sector = self.sector - TRACK2_START_LBA
        if relative_sector < 0:
            raise ValueError("resource descriptor LBA precedes Track 2")
        return relative_sector * 2048


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_resource_name(raw: bytes) -> bool:
    if not raw or len(raw) > RESOURCE_NAME_BYTES:
        return False
    return all(
        0x41 <= value <= 0x5A or 0x30 <= value <= 0x39 or value == 0x5F
        for value in raw
    )


def parse_resource_descriptor_table(
    payload: bytes,
    label: str,
    offset: int,
) -> tuple[ResourceDescriptor, ...]:
    """Parse one fixed 16-byte resource descriptor table until structure ends."""

    rows: list[ResourceDescriptor] = []
    for index in range(256):
        start = offset + index * RESOURCE_DESCRIPTOR_BYTES
        record = payload[start : start + RESOURCE_DESCRIPTOR_BYTES]
        if len(record) != RESOURCE_DESCRIPTOR_BYTES:
            break

        name_field = record[:RESOURCE_NAME_BYTES]
        zero = name_field.find(b"\x00")
        if zero < 0:
            zero = RESOURCE_NAME_BYTES
        name_raw = name_field[:zero]
        if not _is_resource_name(name_raw):
            break
        if any(name_field[zero:]):
            break

        sector = int.from_bytes(record[10:12], "little")
        sector_span = record[12]
        byte_length = int.from_bytes(record[13:16], "little")
        if (
            sector_span == 0
            or byte_length == 0
            or math.ceil(byte_length / 2048) != sector_span
            or sector < TRACK2_START_LBA
            or (sector - TRACK2_START_LBA) * 2048 + byte_length > len(payload)
        ):
            break

        rows.append(
            ResourceDescriptor(
                table_label=label,
                table_offset=offset,
                index=index,
                name=name_raw.decode("ascii"),
                sector=sector,
                sector_span=sector_span,
                byte_length=byte_length,
            )
        )
    if not rows:
        raise ValueError(f"{label}: no resource descriptors found")
    return tuple(rows)


def _decode_information_text(data: bytes, start: int) -> tuple[str, int]:
    end = data.find(b"\x00", start)
    if end < 0:
        raise ValueError("information text record lacks a null terminator")
    raw = data[start:end]
    try:
        text = raw.decode("shift_jis")
    except UnicodeDecodeError as error:
        raise ValueError("information text record has invalid Shift-JIS") from error
    return text, end + 1


def decode_information_stream(
    data: bytes,
    *,
    start: int = 0,
) -> tuple[tuple[dict[str, Any], ...], int]:
    """Decode the shared 0..10 information-page language through opcode 3."""

    commands: list[dict[str, Any]] = []
    cursor = start
    while cursor < len(data):
        command_offset = cursor
        opcode = data[cursor]
        cursor += 1

        if opcode == 0:
            if cursor + 2 > len(data):
                raise ValueError("truncated positioned text command")
            x = data[cursor]
            y = data[cursor + 1]
            cursor += 2
            text, cursor = _decode_information_text(data, cursor)
            commands.append(
                {
                    "offset": command_offset - start,
                    "opcode": 0,
                    "name": "positioned_shift_jis",
                    "x": x,
                    "y": y,
                    "text": text,
                }
            )
            continue

        argument_bytes = INFORMATION_FIXED_ARGUMENT_BYTES.get(opcode)
        if argument_bytes is None:
            raise ValueError(
                f"unsupported information opcode 0x{opcode:02X} "
                f"at relative offset 0x{command_offset - start:X}"
            )
        if cursor + argument_bytes > len(data):
            raise ValueError("truncated information command")
        args = tuple(data[cursor : cursor + argument_bytes])
        cursor += argument_bytes

        row: dict[str, Any] = {
            "offset": command_offset - start,
            "opcode": opcode,
            "name": {
                1: "set_glyph_vram_page",
                2: "set_glyph_delay",
                3: "terminate",
                4: "toggle_display_phase",
                5: "set_periodic_display_update",
                6: "set_position_transient_delay",
                7: "draw_tile_rectangle",
                8: "sync_and_clear_marker",
                9: "wait_for_input",
                10: "display_reset",
            }[opcode],
            "arguments": list(args),
            "behavior": INFORMATION_COMMAND_SEMANTICS[opcode],
        }
        if opcode in (1, 2, 5):
            row["value"] = args[0]
        elif opcode == 6:
            row.update(x=args[0], y=args[1], transient_delay=args[2])
        elif opcode == 7:
            row.update(
                mode=args[0],
                x=args[1],
                y=args[2],
                width=args[3],
                height=args[4],
            )
        commands.append(row)
        if opcode == 3:
            return tuple(commands), cursor

    raise ValueError("information command stream lacks opcode 3 terminator")


def find_information_streams(payload: bytes) -> tuple[dict[str, Any], ...]:
    results: list[dict[str, Any]] = []
    cursor = 0
    while True:
        offset = payload.find(INFORMATION_STREAM_HEADER, cursor)
        if offset < 0:
            break
        commands, end = decode_information_stream(payload, start=offset)
        results.append(
            {
                "offset": f"0x{offset:08X}",
                "bank": bank_for_offset(offset),
                "bytes": end - offset,
                "sha256": _sha256(payload[offset:end]),
                "commands": len(commands),
                "text_records": sum(
                    item["opcode"] == 0 for item in commands
                ),
                "opcodes": [item["opcode"] for item in commands],
            }
        )
        cursor = end
    return tuple(results)


def validate_information_parser_copies(payload: bytes) -> dict[str, Any]:
    canonical = payload[
        INFORMATION_PARSER_OFFSET :
        INFORMATION_PARSER_OFFSET + INFORMATION_PARSER_LENGTH
    ]
    digest = _sha256(canonical)
    rows = []
    for offset in INFORMATION_PARSER_COPY_OFFSETS:
        actual = payload[offset : offset + INFORMATION_PARSER_LENGTH]
        rows.append(
            {
                "offset": f"0x{offset:08X}",
                "bank": bank_for_offset(offset),
                "matched": actual == canonical,
                "sha256": _sha256(actual),
            }
        )

    dispatcher_signature = bytes.fromhex("B2 00 0A AA 7C")
    variant_rows = []
    for offset in INFORMATION_VARIANT_DISPATCH_OFFSETS:
        actual = payload[offset : offset + len(dispatcher_signature)]
        variant_rows.append(
            {
                "offset": f"0x{offset:08X}",
                "bank": bank_for_offset(offset),
                "dispatcher_shape_matches": actual == dispatcher_signature
                or (
                    len(actual) == len(dispatcher_signature)
                    and actual[0] == 0xB2
                    and actual[2:] == dispatcher_signature[2:]
                ),
                "pointer_zp": f"0x{actual[1]:02X}" if len(actual) >= 2 else None,
            }
        )

    return {
        "canonical_offset": f"0x{INFORMATION_PARSER_OFFSET:08X}",
        "canonical_length": INFORMATION_PARSER_LENGTH,
        "canonical_sha256": digest,
        "canonical_hash_matches": digest == INFORMATION_PARSER_SHA256,
        "byte_identical_copies": rows,
        "all_common_copies_match": all(row["matched"] for row in rows),
        "early_variants": variant_rows,
    }


def _looks_like_japanese_text(text: str) -> bool:
    if len(text) < 4:
        return False
    useful = 0
    for character in text:
        code = ord(character)
        if (
            0x3040 <= code <= 0x30FF
            or 0x3400 <= code <= 0x9FFF
            or 0xFF01 <= code <= 0xFF60
            or character in "　、。・ー（）「」『』"
        ):
            useful += 1
        elif character.isspace():
            useful += 1
        else:
            return False
    return useful == len(text)


def count_direct_shift_jis_strings(data: bytes) -> int:
    """Count conservative null-terminated Japanese strings in a binary asset."""

    matches: set[tuple[int, str]] = set()
    for start in range(len(data)):
        first = data[start]
        if not (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xFC):
            continue
        end = data.find(b"\x00", start + 2, min(len(data), start + 192))
        if end < 0:
            continue
        raw = data[start:end]
        if len(raw) < 8:
            continue
        try:
            text = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if _looks_like_japanese_text(text):
            matches.add((start, text))
    return len(matches)


def validate_m0b_runtime_regions(payload: bytes) -> tuple[dict[str, Any], ...]:
    rows = []
    for name, offset, length, expected_hash, purpose in M0B_RUNTIME_REGIONS:
        actual = payload[offset : offset + length]
        digest = _sha256(actual)
        rows.append(
            {
                "name": name,
                "offset": f"0x{offset:08X}",
                "length": length,
                "sha256": digest,
                "matched": digest == expected_hash and len(actual) == length,
                "purpose": purpose,
            }
        )
    return tuple(rows)


def build_resource_descriptor_report(payload: bytes) -> dict[str, Any]:
    tables = []
    target_assets = []
    for label, offset in RESOURCE_DESCRIPTOR_TABLES:
        descriptors = parse_resource_descriptor_table(payload, label, offset)
        tables.append(
            {
                "label": label,
                "offset": f"0x{offset:08X}",
                "entries": len(descriptors),
                "sha256": _sha256(
                    payload[
                        offset : offset + len(descriptors) * RESOURCE_DESCRIPTOR_BYTES
                    ]
                ),
            }
        )
        for descriptor in descriptors:
            if descriptor.name not in RESOURCE_UI_ASSET_NAMES:
                continue
            blob = payload[
                descriptor.payload_offset :
                descriptor.payload_offset + descriptor.byte_length
            ]
            target_assets.append(
                {
                    "table": label,
                    "name": descriptor.name,
                    "descriptor_offset": f"0x{descriptor.record_offset:08X}",
                    "sector": f"0x{descriptor.sector:04X}",
                    "sector_span": descriptor.sector_span,
                    "byte_length": descriptor.byte_length,
                    "payload_offset": f"0x{descriptor.payload_offset:08X}",
                    "sha256": _sha256(blob),
                    "direct_shift_jis_strings": count_direct_shift_jis_strings(blob),
                }
            )
    return {
        "record_format": {
            "bytes": RESOURCE_DESCRIPTOR_BYTES,
            "name": "10-byte NUL-padded ASCII",
            "sector": "u16 little-endian Track 2 sector",
            "sector_span": "u8",
            "byte_length": "u24 little-endian",
        },
        "tables": tables,
        "named_ui_assets": target_assets,
        "all_named_ui_assets_lack_direct_shift_jis": all(
            row["direct_shift_jis_strings"] == 0 for row in target_assets
        ),
    }


def translation_ownership_map() -> tuple[dict[str, Any], ...]:
    return (
        {
            "family": "common_dialogue",
            "lifetime": "mission text overlay / dialogue resource occurrence",
            "addressing": "mixed bytecode stream; relocated overlay parser",
            "current_capacity": "occurrence-specific",
            "safe_policy": (
                "edit occurrence text under source guards; arbitrary growth stays "
                "relocation-gated until owned destination storage is proven"
            ),
        },
        {
            "family": "dynamic_labels",
            "lifetime": "disc source -> 24-record runtime table at $A400",
            "addressing": "indexed 32-byte records selected by opcode 3D",
            "current_capacity": "two 13-byte slots including terminator",
            "safe_policy": "fixed-field replacement is safe; growth requires table redesign",
        },
        {
            "family": "command_system_ui",
            "lifetime": "common M0-B/M1-M8 text overlay",
            "addressing": "37 fixed 16-byte records",
            "current_capacity": "16 bytes including metadata and terminator",
            "safe_policy": "preserve per-entry metadata and fixed record stride",
        },
        {
            "family": "information_pages",
            "lifetime": "startup or mission/ending information-page stream",
            "addressing": "0..10 command language with positioned Shift-JIS records",
            "current_capacity": "stream-local; command offsets move when text grows",
            "safe_policy": (
                "stream rewriting is structurally understood; relocation remains "
                "gated on each caller/source-pointer ownership proof"
            ),
        },
        {
            "family": "opening_dossiers",
            "lifetime": "opening presentation, duplicated source copies",
            "addressing": "row-addressed fixed source records",
            "current_capacity": "guarded source fields/build profile",
            "safe_policy": "use the existing dossier build profile and preserve row commands",
        },
        {
            "family": "ending_completion_and_credits",
            "lifetime": "ENDING presentation overlay",
            "addressing": "opcodes 0/1 Shift-JIS, opcode 2 ASCII, FF terminator",
            "current_capacity": "contiguous guarded stream",
            "safe_policy": (
                "same-size edits are structurally safe; growth is gated on the "
                "owning stream pointer/boundary contract"
            ),
        },
        {
            "family": "named_binary_ui_assets",
            "lifetime": "on-demand resource cache/install path",
            "addressing": "16-byte name -> sector/span/length descriptors",
            "current_capacity": "exact descriptor byte length",
            "safe_policy": (
                "do not treat as text; preserve binary format until the individual "
                "asset schema is decoded"
            ),
        },
        {
            "family": "opening_title_graphic",
            "lifetime": "startup title presentation",
            "addressing": "fixed 960-tile planar graphic",
            "current_capacity": TITLE_ASSET_BYTES,
            "safe_policy": "replace through the tested graphics pipeline, not text relocation",
        },
    )


def build_completion_report(path: pathlib.Path) -> dict[str, Any]:
    payload = path.read_bytes()
    authenticated = sha256_file(path) == TRACK2_PAYLOAD_SHA256
    parser = validate_information_parser_copies(payload)
    streams = find_information_streams(payload)
    descriptors = build_resource_descriptor_report(payload)
    runtime = validate_m0b_runtime_regions(payload)
    return {
        "scope": "text-engine completion: information pages, resource ownership, relocation",
        "payload_authenticated": authenticated,
        "information_language": {
            "commands": {
                str(opcode): meaning
                for opcode, meaning in INFORMATION_COMMAND_SEMANTICS.items()
            },
            "parser": parser,
            "streams": streams,
            "stream_count": len(streams),
            "ending_oedonet_offset": f"0x{ENDING_OEDONET_STREAM.offset:08X}",
            "ending_oedonet_is_shared_language": any(
                row["offset"] == f"0x{ENDING_OEDONET_STREAM.offset:08X}"
                for row in streams
            ),
        },
        "resource_descriptors": descriptors,
        "m0b_runtime_resource_path": runtime,
        "translation_ownership": translation_ownership_map(),
        "remaining_live_certification": {
            "mission_0": (
                "historical Mesen captures already exist and show the real parser, "
                "renderer/font path, CD loads, and MPR changes"
            ),
            "missions_1_8": "new representative Mesen capture still required",
            "ending": "new information/credits Mesen capture still required",
        },
        "limits": {
            "named_binary_assets": (
                "absence of direct Shift-JIS is proven conservatively; their "
                "individual binary/graphics schemas are not inferred"
            ),
            "information_early_variants": (
                "three earlier dispatchers share the same indirect-dispatch shape; "
                "their complete handler bodies are not claimed byte-identical"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate shared information-page commands and named resource "
            "ownership needed to finish the game-wide text-engine map."
        )
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_completion_report(args.payload)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    ok = (
        report["payload_authenticated"]
        and report["information_language"]["parser"]["canonical_hash_matches"]
        and report["information_language"]["parser"]["all_common_copies_match"]
        and report["information_language"]["ending_oedonet_is_shared_language"]
        and report["information_language"]["stream_count"] >= 11
        and report["resource_descriptors"]["all_named_ui_assets_lack_direct_shift_jis"]
        and all(item["matched"] for item in report["m0b_runtime_resource_path"])
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
