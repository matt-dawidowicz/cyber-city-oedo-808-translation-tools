"""Prove the Mission 0 dialogue interpreter against source bytes.

Tier B begins with runtime-engine evidence, not a new patch.  This module
captures the smallest source-guarded code regions needed to reproduce the
known dialogue dispatch and the ``3D`` indexed-text path.  It deliberately
keeps the historical zero-filled region classified as unowned until runtime
or loader evidence proves otherwise.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import pathlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cyber_oedo.disc.game_layout import SECTOR_SIZE, TRACK2_START_LBA

MISSION0_MODULE_PAYLOAD_BASE = 0x00131800
DIALOGUE_INTERPRETER_CPU = 0x9543
INDIRECT_TEXT_HANDLER_CPU = 0x958F
INDEXED_RECORD_ROUTINE_CPU = 0x6694
INDEXED_FIELD_RENDERER_CPU = 0x960F
GLYPH_CELL_RENDERER_CPU = 0x5915
STREAM_READ_CPU = 0x9F11
STREAM_ADVANCE_CPU = 0x9F14
INDEXED_TABLE_LOADER_CPU = 0x64CB
CD_READ_ORCHESTRATOR_CPU = 0x6EBE
CD_READ_TRANSFER_CPU = 0x6F50
INDEXED_STATE_DISPATCH_CPU = 0x9060
INDEXED_STATE_SETTER_CPU = 0x94A4
INDEXED_STATE_WRITE_CPU = 0x66F9
HISTORICAL_ZERO_REGION_CPU = 0x9F1B
HISTORICAL_ZERO_REGION_SIZE = 0xE5
INDEXED_RECORD_BASE = 0xA400
INDEXED_RECORD_STRIDE = 0x20
INDEXED_STATE_OFFSET = 0x1A
INDEXED_TEXT_SLOT_BYTES = 0x0D
INDEXED_ALTERNATE_TEXT_OFFSET = 0x0D
INDEXED_TABLE_ABSOLUTE_LBA = 0x107D
INDEXED_TABLE_TRANSFER_BYTES = 0x0301
INDEXED_TABLE_RECORD_COUNT = 0x18
INDEXED_TABLE_TRAILER_BYTES = 1
INDEXED_TABLE_SOURCE_SHA256 = (
    "385fe67174f28f54787e9372b5ef865a34ab7f040ed46affd95c425f35d54576"
)
TRACK2_PAYLOAD_SHA256 = (
    "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"
)


@dataclass(frozen=True, slots=True)
class RuntimeRegion:
    """Describe one exact source-guarded Mission 0 runtime region."""

    name: str
    cpu_address: int
    expected: bytes
    purpose: str
    ownership_proven: bool = True

    @property
    def payload_offset(self) -> int:
        """Return the Track 2 payload offset for the region."""

        return cpu_to_payload(self.cpu_address)


RUNTIME_REGIONS = (
    RuntimeRegion(
        "parser_entry",
        DIALOGUE_INTERPRETER_CPU,
        bytes.fromhex("20 11 9F 20 14 9F A8 D0 01 60"),
        "Read one stream byte, advance the pointer, and stop on zero.",
    ),
    RuntimeRegion(
        "indirect_text_handler",
        INDIRECT_TEXT_HANDLER_CPU,
        bytes.fromhex(
            "C9 3D D0 2C 20 FC 8C 20 11 9F 20 14 9F "
            "20 11 9F 20 14 9F 85 00 20 94 66 A0 1A "
            "B1 00 D0 0D A5 00 18 69 0D 85 00 A5 01 "
            "69 00 85 01 20 0F 96 80 84"
        ),
        (
            "Consume two 3D operands, index a 32-byte record, select one "
            "of two text fields, render it, and resume the stream."
        ),
    ),
    RuntimeRegion(
        "indexed_record_address",
        INDEXED_RECORD_ROUTINE_CPU,
        bytes.fromhex(
            "C6 00 A9 20 85 01 64 18 64 19 A5 01 85 1A "
            "64 1B A0 08 66 00 90 0A 18 A2 18 F4 65 1A "
            "E8 F4 65 1B 18 26 1A 26 1B 88 D0 EA A5 18 "
            "85 00 A5 19 85 01 A5 00 18 69 00 85 00 A5 "
            "01 69 A4 85 01 60"
        ),
        (
            "Compute A400 + ((index - 1) & FF) * 20 using HuC6280 "
            "T-flag memory arithmetic."
        ),
    ),
    RuntimeRegion(
        "indexed_field_renderer",
        INDEXED_FIELD_RENDERER_CPU,
        bytes.fromhex(
            "B2 00 D0 01 60 85 03 E6 00 D0 02 E6 01 B2 "
            "00 85 02 E6 00 D0 02 E6 01 20 15 59 80 E4"
        ),
        "Render null-terminated two-byte glyph pairs through $5915.",
    ),
    RuntimeRegion(
        "stream_helpers",
        STREAM_READ_CPU,
        bytes.fromhex("B2 7F 60 E6 7F D0 02 E6 80 60"),
        "Read from ($7F) and advance the 16-bit stream pointer.",
    ),
    RuntimeRegion(
        "indexed_table_loader",
        INDEXED_TABLE_LOADER_CPU,
        bytes.fromhex(
            "A9 00 85 00 A9 A4 85 01 A9 00 85 02 A9 7D 85 04 "
            "A9 10 85 05 A9 01 85 06 A9 03 85 07 20 A0 6E 60"
        ),
        ("Request a 0x301-byte CD transfer into $A400 from absolute LBA $107D."),
    ),
    RuntimeRegion(
        "cd_read_orchestrator",
        CD_READ_ORCHESTRATOR_CPU,
        bytes.fromhex("A5 07 4A 4A 4A 85 08 A5 08 F0 03 20 50 6F 20 73 6F"),
        ("Split a byte count into 0x800-byte CD blocks and a remainder path."),
    ),
    RuntimeRegion(
        "cd_read_transfer",
        CD_READ_TRANSFER_CPU,
        bytes.fromhex(
            "A5 02 85 FC A5 05 85 FD A5 04 85 FE A9 01 85 FF "
            "A5 00 85 FA A5 01 85 FB A5 08 85 F8 20 09 E0 "
            "A8 D0 DE 60"
        ),
        ("Populate the System Card CD_READ argument block and call $E009."),
    ),
    RuntimeRegion(
        "indexed_state_dispatch",
        INDEXED_STATE_DISPATCH_CPU,
        bytes.fromhex("2F A4 94"),
        "Map outer script opcode 2F to the indexed-record state setter.",
    ),
    RuntimeRegion(
        "indexed_state_setter",
        INDEXED_STATE_SETTER_CPU,
        bytes.fromhex("20 11 9F 20 14 9F 85 00 20 F9 66 60"),
        "Read one record index and call the state-byte write helper.",
    ),
    RuntimeRegion(
        "indexed_state_write",
        INDEXED_STATE_WRITE_CPU,
        bytes.fromhex("20 94 66 A0 1A A9 FF 91 00 60"),
        "Write FF to byte 1A of one indexed 32-byte record.",
    ),
    RuntimeRegion(
        "historical_zero_region",
        HISTORICAL_ZERO_REGION_CPU,
        bytes(HISTORICAL_ZERO_REGION_SIZE),
        (
            "Historical Stage 1 injection area; zero-filled is not "
            "resource ownership proof."
        ),
        ownership_proven=False,
    ),
)


def cpu_to_payload(cpu_address: int) -> int:
    """Translate one Mission 0 logical CPU address to payload coordinates."""

    if not isinstance(cpu_address, int) or isinstance(cpu_address, bool):
        raise TypeError("CPU address must be an integer")
    if not 0 <= cpu_address < 0xA000:
        raise ValueError("CPU address must lie in the mapped module range")
    return MISSION0_MODULE_PAYLOAD_BASE + cpu_address


def indexed_record_address(index: int) -> int:
    """Reproduce the exact one-byte record-index calculation at ``$6694``."""

    if not isinstance(index, int) or isinstance(index, bool):
        raise TypeError("record index must be an integer")
    if not 0 <= index <= 0xFF:
        raise ValueError("record index must fit in one byte")
    normalized = (index - 1) & 0xFF
    return (INDEXED_RECORD_BASE + normalized * INDEXED_RECORD_STRIDE) & 0xFFFF


def indexed_text_field_offset(state_byte: int) -> int:
    """Return the selected text-field offset from the record state byte."""

    if not isinstance(state_byte, int) or isinstance(state_byte, bool):
        raise TypeError("state byte must be an integer")
    if not 0 <= state_byte <= 0xFF:
        raise ValueError("state byte must fit in one byte")
    if state_byte:
        return 0
    return INDEXED_ALTERNATE_TEXT_OFFSET


def absolute_lba_to_payload_offset(absolute_lba: int) -> int:
    """Convert one absolute Track 2 LBA to a payload byte offset."""

    if not isinstance(absolute_lba, int) or isinstance(absolute_lba, bool):
        raise TypeError("absolute LBA must be an integer")
    relative_sector = absolute_lba - TRACK2_START_LBA
    if relative_sector < 0:
        raise ValueError("absolute LBA precedes Track 2")
    return relative_sector * SECTOR_SIZE


def indexed_table_source_offset() -> int:
    """Return the authenticated payload offset loaded into ``$A400``."""

    return absolute_lba_to_payload_offset(INDEXED_TABLE_ABSOLUTE_LBA)


def _decode_record_field(record: bytes, start: int) -> str:
    """Decode one fixed 13-byte Shift-JIS text slot from an indexed record."""

    end = start + INDEXED_TEXT_SLOT_BYTES
    slot = record[start:end]
    terminator = slot.find(b"\x00")
    if terminator < 0:
        raise ValueError("indexed text slot is not null-terminated")
    return slot[:terminator].decode("shift_jis")


def indexed_table_evidence(path: pathlib.Path) -> dict[str, Any]:
    """Validate and summarize the Mission 0 indexed-record source table."""

    offset = indexed_table_source_offset()
    with path.open("rb") as source:
        source.seek(offset)
        table = source.read(INDEXED_TABLE_TRANSFER_BYTES)
    if len(table) != INDEXED_TABLE_TRANSFER_BYTES:
        raise ValueError("indexed table source is truncated")

    records_blob = table[:-INDEXED_TABLE_TRAILER_BYTES]
    expected_records_bytes = INDEXED_TABLE_RECORD_COUNT * INDEXED_RECORD_STRIDE
    if len(records_blob) != expected_records_bytes:
        raise ValueError("indexed table source has an unexpected size")

    records = tuple(
        records_blob[index : index + INDEXED_RECORD_STRIDE]
        for index in range(0, len(records_blob), INDEXED_RECORD_STRIDE)
    )
    slots_terminated = True
    for record in records:
        if b"\x00" not in record[:INDEXED_TEXT_SLOT_BYTES]:
            slots_terminated = False
        alternate_end = INDEXED_ALTERNATE_TEXT_OFFSET + INDEXED_TEXT_SLOT_BYTES
        if b"\x00" not in record[INDEXED_ALTERNATE_TEXT_OFFSET:alternate_end]:
            slots_terminated = False

    maya_record = records[5]
    return {
        "absolute_lba": f"0x{INDEXED_TABLE_ABSOLUTE_LBA:04X}",
        "track2_relative_sector": (
            f"0x{INDEXED_TABLE_ABSOLUTE_LBA - TRACK2_START_LBA:03X}"
        ),
        "payload_offset": f"0x{offset:08X}",
        "transfer_bytes": INDEXED_TABLE_TRANSFER_BYTES,
        "record_count": len(records),
        "record_stride": INDEXED_RECORD_STRIDE,
        "trailer_bytes": INDEXED_TABLE_TRAILER_BYTES,
        "trailer_hex": table[-INDEXED_TABLE_TRAILER_BYTES:].hex(),
        "sha256": hashlib.sha256(table).hexdigest(),
        "sha256_matched": (
            hashlib.sha256(table).hexdigest() == INDEXED_TABLE_SOURCE_SHA256
        ),
        "all_text_slots_null_terminated": slots_terminated,
        "record_06": {
            "cpu_address": f"0x{indexed_record_address(6):04X}",
            "primary_text": _decode_record_field(maya_record, 0),
            "alternate_text": _decode_record_field(
                maya_record,
                INDEXED_ALTERNATE_TEXT_OFFSET,
            ),
            "state_byte": maya_record[INDEXED_STATE_OFFSET],
            "sha256": hashlib.sha256(maya_record).hexdigest(),
        },
    }


def hash_file(path: pathlib.Path) -> str:
    """Return the lowercase SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_runtime_regions(path: pathlib.Path) -> tuple[dict[str, Any], ...]:
    """Validate every Tier-B runtime source guard against a payload."""

    results: list[dict[str, Any]] = []
    with path.open("rb") as source:
        for region in RUNTIME_REGIONS:
            source.seek(region.payload_offset)
            actual = source.read(len(region.expected))
            matched = actual == region.expected
            results.append(
                {
                    "name": region.name,
                    "cpu_address": f"0x{region.cpu_address:04X}",
                    "payload_offset": (f"0x{region.payload_offset:08X}"),
                    "bytes": len(region.expected),
                    "sha256": hashlib.sha256(actual).hexdigest(),
                    "matched": matched,
                    "ownership_proven": region.ownership_proven,
                    "purpose": region.purpose,
                }
            )
    return tuple(results)


def _three_d_patterns(path: pathlib.Path) -> dict[str, Any]:
    """Summarize ``3D arg0 arg1`` evidence from a Tier-A dialogue TSV."""

    patterns: collections.Counter[tuple[int, int]] = collections.Counter()
    rows_with_3d = 0
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if "controls" not in (reader.fieldnames or ()):
            raise ValueError("dialogue TSV is missing the controls column")
        for row in reader:
            tokens = row["controls"].split()
            row_had_3d = False
            for index, token in enumerate(tokens):
                if token.upper() != "3D":
                    continue
                if index + 2 >= len(tokens):
                    raise ValueError("truncated 3D operands in dialogue TSV")
                arg0 = int(tokens[index + 1], 16)
                arg1 = int(tokens[index + 2], 16)
                patterns[(arg0, arg1)] += 1
                row_had_3d = True
            if row_had_3d:
                rows_with_3d += 1
    return {
        "rows_with_3d": rows_with_3d,
        "occurrences": sum(patterns.values()),
        "patterns": [
            {
                "arg0": f"0x{arg0:02X}",
                "arg1": f"0x{arg1:02X}",
                "record_cpu": f"0x{indexed_record_address(arg1):04X}",
                "count": count,
            }
            for (arg0, arg1), count in sorted(patterns.items())
        ],
    }


def build_runtime_report(
    payload: pathlib.Path,
    dialogue: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Build a deterministic Tier-B static-runtime proof report."""

    payload_digest = hash_file(payload)
    regions = validate_runtime_regions(payload)
    table = indexed_table_evidence(payload)
    report: dict[str, Any] = {
        "tier": "B2-static",
        "scope": ("Mission 0 dialogue interpreter and indexed-table loader proof"),
        "payload_sha256": payload_digest,
        "payload_authenticated": payload_digest == TRACK2_PAYLOAD_SHA256,
        "all_source_guards_match": all(item["matched"] for item in regions),
        "regions": regions,
        "indexed_table_loader": table,
        "three_d_static_semantics": {
            "operand_bytes": 2,
            "arg0_runtime_use": "read and discarded in this interpreter",
            "arg1_runtime_use": "one-based 32-byte record index",
            "record_table_cpu_base": f"0x{INDEXED_RECORD_BASE:04X}",
            "record_stride": INDEXED_RECORD_STRIDE,
            "state_byte_offset": INDEXED_STATE_OFFSET,
            "state_set_by_outer_script_opcode": "0x2F",
            "state_set_value": "0xFF",
            "primary_text_offset": 0,
            "alternate_text_offset": INDEXED_ALTERNATE_TEXT_OFFSET,
            "field_renderer_cpu": f"0x{INDEXED_FIELD_RENDERER_CPU:04X}",
            "glyph_renderer_cpu": f"0x{GLYPH_CELL_RENDERER_CPU:04X}",
        },
        "ownership": {
            "historical_zero_region_cpu": (f"0x{HISTORICAL_ZERO_REGION_CPU:04X}"),
            "zero_filled": next(
                item["matched"]
                for item in regions
                if item["name"] == "historical_zero_region"
            ),
            "ownership_proven": False,
        },
    }
    if dialogue is not None:
        report["three_d_disc_evidence"] = _three_d_patterns(dialogue)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the Tier-B runtime-proof command parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate Mission 0 dialogue runtime guards and emit a "
            "Tier-B static proof report."
        )
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument(
        "--dialogue",
        type=pathlib.Path,
        help="optional Tier-A dialogue TSV for 3D operand statistics",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="optional JSON destination; stdout is always summarized",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate static runtime evidence and optionally write JSON."""

    args = build_parser().parse_args(argv)
    report = build_runtime_report(args.payload, args.dialogue)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"payload_authenticated={report['payload_authenticated']}")
    print(f"all_source_guards_match={report['all_source_guards_match']}")
    table = report["indexed_table_loader"]
    print(f"indexed_table_sha256_matched={table['sha256_matched']}")
    print(f"indexed_table_records={table['record_count']}")
    evidence = report.get("three_d_disc_evidence")
    if evidence is not None:
        print(f"three_d_occurrences={evidence['occurrences']}")
        print(f"three_d_patterns={len(evidence['patterns'])}")
    print("historical_zero_region_ownership_proven=False")
    if not report["payload_authenticated"]:
        return 1
    if not report["all_source_guards_match"]:
        return 1
    if not table["sha256_matched"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
