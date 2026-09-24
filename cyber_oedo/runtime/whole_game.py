"""Whole-game reverse-engineering evidence beyond the text/movement cores."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256


SAVE_COMMON_MODULES = (
    ("MISSION_1", 0x00CC4000),
    ("MISSION_2", 0x01793800),
    ("MISSION_3", 0x0220C000),
    ("MISSION_4", 0x02AFC000),
    ("MISSION_5", 0x03336800),
    ("MISSION_6", 0x03B14000),
    ("MISSION_7", 0x04261800),
    ("MISSION_8", 0x04828000),
    ("ENDING", 0x05008800),
)
SAVE_WRITE_REL = 0x4000
SAVE_WRITE_BYTES = 0xA2
SAVE_WRITE_SHA256 = "6fbb98101fc13122e525e42925b0d7d90a0f022c1d0fe89032a26d35cd605728"
SAVE_READ_REL = 0x5FA0
SAVE_READ_BYTES = 0xF0
SAVE_READ_SHA256 = "8a1253affa4048a7e4f42ad50af1a6c9e6b470a9c8f2682b94598ce150b2c0f5"

BOOT_SAVE_READ_OFFSET = 0x00003FA0
BOOT_SAVE_READ_BYTES = 0xE0
BOOT_SAVE_READ_SHA256 = "e50a4c01da3dee19d11bdfbd6c05086e1391aac251749d282ad59a3c744f2ef8"
BOOT_SLOT_CONSUMER_OFFSET = 0x000019F1
BOOT_SLOT_CONSUMER_BYTES = 0x110
BOOT_SLOT_CONSUMER_SHA256 = "2796c27ffdacb966af5065ae308ce4d8fb7b184d63484d27d0efe98a4784bf5c"
BOOT_EVENT_LOADER_OFFSET = 0x00001AD3
BOOT_EVENT_LOADER_BYTES = 0x41
BOOT_EVENT_LOADER_SHA256 = "af9dcecd7d068422f2b33a40b9e4deac0a89b21e7e92267a437b56ad55810708"

TRACK2_START_LBA = 3590
BOOT_EVENT_ABSOLUTE_LBA = 0x106F
EVENT_OVERLAY_OFFSET = (BOOT_EVENT_ABSOLUTE_LBA - TRACK2_START_LBA) * 2048
EVENT_OVERLAY_BYTES = 0x800
EVENT_OVERLAY_SHA256 = "197cc4ff5bda6978a14db6406d19c8995be2952068196abc7e22073cbefa813e"
EVENT_TABLE_A_CPU = 0xD803
EVENT_TABLE_A_RECORDS = 9
EVENT_TABLE_B_CPU = 0xD827
EVENT_TABLE_B_RECORDS = 9
EVENT_TABLE_C_CPU = 0xD8CA
EVENT_TABLE_C_RECORDS = 10
EVENT_DISPATCH_TABLE_CPU = 0xD881

SAVE_FILE_DESCRIPTOR = bytes.fromhex("07 00") + b"OEDO808   "
SAVE_SLOT_BYTES = 4
SAVE_RUNTIME_BUFFER = "$268F-$2692"
BOOT_SAVE_BUFFER = "$2E91-$2E94"
PROGRESS_SELECTOR = "$371F"

ADPCM_MODULE_BASE = 0x02230800
ADPCM_START_CPU = 0x8108
ADPCM_START_BYTES = 0x20
ADPCM_START_SHA256 = "92cf4de93f46d8d8572fd4bf9baf3d5a806f591bae8978a590400a1069ae5da8"
ADPCM_COMPLETION_CPU = 0x837A
ADPCM_COMPLETION_BYTES = 0x16
ADPCM_COMPLETION_SHA256 = "fca694052876a354d584434cda2278c6f5d6746d2062c07bb0916c2e55e07c10"
ADPCM_LOOKUP_CPU = 0x8471
ADPCM_LOOKUP_BYTES = 0xD4
ADPCM_LOOKUP_SHA256 = "40640359481c40926785bc88456770aefbd876aa5c872500f8a7c698d51270ad"
ADPCM_TABLE_CPU = 0x8BA2
ADPCM_RECORD_BYTES = 6
ADPCM_PROVEN_RECORDS = 64
ADPCM_TABLE_BYTES = ADPCM_RECORD_BYTES * ADPCM_PROVEN_RECORDS
ADPCM_TABLE_SHA256 = "7437807ea9aee0ecdc6bc1a9b9dbc2599e778754531b54320e52bae581ef6514"

OBJECT_SCRATCH_BASE = 0x2823
OBJECT_LIVE_BASE = 0x2783
OBJECT_LIVE_BYTES = 16
OBJECT_SOURCE_BYTES = 8
INTERACTION_RESULT_BASE = 0x3703
INTERACTION_RESULT_BYTES = 9


@dataclass(frozen=True, slots=True)
class GuardedRegion:
    name: str
    offset: int
    length: int
    sha256: str
    purpose: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _guard(payload: bytes, region: GuardedRegion) -> dict[str, Any]:
    actual = payload[region.offset : region.offset + region.length]
    digest = _sha256(actual)
    return {
        "name": region.name,
        "offset": f"0x{region.offset:08X}",
        "length": region.length,
        "sha256": digest,
        "matched": len(actual) == region.length and digest == region.sha256,
        "purpose": region.purpose,
    }


def _save_report(payload: bytes) -> dict[str, Any]:
    copies = []
    for label, base in SAVE_COMMON_MODULES:
        write = payload[base + SAVE_WRITE_REL : base + SAVE_WRITE_REL + SAVE_WRITE_BYTES]
        read = payload[base + SAVE_READ_REL : base + SAVE_READ_REL + SAVE_READ_BYTES]
        descriptor = payload[base + 0x6088 : base + 0x6088 + len(SAVE_FILE_DESCRIPTOR)]
        copies.append(
            {
                "label": label,
                "module_base": f"0x{base:08X}",
                "write_sha256": _sha256(write),
                "write_matches": _sha256(write) == SAVE_WRITE_SHA256,
                "read_sha256": _sha256(read),
                "read_matches": _sha256(read) == SAVE_READ_SHA256,
                "file_descriptor_hex": descriptor.hex(),
                "file_descriptor_matches": descriptor == SAVE_FILE_DESCRIPTOR,
            }
        )

    boot_regions = (
        GuardedRegion(
            "boot_bram_read",
            BOOT_SAVE_READ_OFFSET,
            BOOT_SAVE_READ_BYTES,
            BOOT_SAVE_READ_SHA256,
            "Read four OEDO808 slot bytes into $2E91-$2E94 and classify BIOS status.",
        ),
        GuardedRegion(
            "boot_slot_consumer",
            BOOT_SLOT_CONSUMER_OFFSET,
            BOOT_SLOT_CONSUMER_BYTES,
            BOOT_SLOT_CONSUMER_SHA256,
            "Reject zero as empty, copy selected slot to $371F, and select initial/resume path.",
        ),
    )

    return {
        "file_descriptor": {
            "bytes_hex": SAVE_FILE_DESCRIPTOR.hex(),
            "ascii_name": "OEDO808   ",
            "leading_bytes": "07 00",
        },
        "slot_count": SAVE_SLOT_BYTES,
        "bytes_per_slot": 1,
        "runtime_buffer": SAVE_RUNTIME_BUFFER,
        "boot_buffer": BOOT_SAVE_BUFFER,
        "progress_selector": PROGRESS_SELECTOR,
        "semantics": {
            "empty_slot": 0,
            "saved_value": "current $371F progress/mission selector; zero is coerced to 1",
            "write_behavior": (
                "fresh-state path clears all four bytes; selected slot is replaced; "
                "BM_WRITE writes exactly four bytes"
            ),
            "load_behavior": (
                "BM_READ reads exactly four bytes; boot indexes the chosen slot and "
                "copies a nonzero byte to $371F"
            ),
            "checksum": (
                "no explicit game-side checksum appears in the guarded wrappers; "
                "BIOS backup-memory status supplies error handling"
            ),
        },
        "common_copies": copies,
        "boot_regions": tuple(_guard(payload, region) for region in boot_regions),
    }



def _decode_cd_descriptor(raw: bytes, index: int) -> dict[str, Any]:
    if len(raw) != 4:
        raise ValueError("CD descriptor must be four bytes")
    lba = raw[1] | raw[2] << 8 | raw[0] << 16
    return {
        "index": index,
        "raw_hex": raw.hex(),
        "absolute_lba": "0x%06X" % lba,
        "track2_relative_sector": lba - TRACK2_START_LBA,
        "block_count": raw[3],
    }


def _event_control_report(payload: bytes) -> dict[str, Any]:
    block = payload[EVENT_OVERLAY_OFFSET : EVENT_OVERLAY_OFFSET + EVENT_OVERLAY_BYTES]
    if len(block) != EVENT_OVERLAY_BYTES:
        raise ValueError("event overlay block is truncated")

    table_a_offset = EVENT_TABLE_A_CPU - 0xD800
    table_b_offset = EVENT_TABLE_B_CPU - 0xD800
    table_c_offset = EVENT_TABLE_C_CPU - 0xD800
    dispatch_offset = EVENT_DISPATCH_TABLE_CPU - 0xD800

    table_a = tuple(
        _decode_cd_descriptor(
            block[table_a_offset + i * 4 : table_a_offset + (i + 1) * 4],
            i,
        )
        for i in range(EVENT_TABLE_A_RECORDS)
    )
    table_b = tuple(
        _decode_cd_descriptor(
            block[table_b_offset + i * 4 : table_b_offset + (i + 1) * 4],
            i,
        )
        for i in range(EVENT_TABLE_B_RECORDS)
    )
    table_c = tuple(
        _decode_cd_descriptor(
            block[table_c_offset + i * 4 : table_c_offset + (i + 1) * 4],
            i,
        )
        for i in range(EVENT_TABLE_C_RECORDS)
    )
    dispatch = tuple(
        int.from_bytes(
            block[dispatch_offset + i * 2 : dispatch_offset + (i + 1) * 2],
            "little",
        )
        for i in range(7)
    )

    return {
        "overlay": {
            "absolute_lba": "0x%04X" % BOOT_EVENT_ABSOLUTE_LBA,
            "track2_start_lba": TRACK2_START_LBA,
            "payload_offset": "0x%08X" % EVENT_OVERLAY_OFFSET,
            "bytes": EVENT_OVERLAY_BYTES,
            "sha256": _sha256(block),
            "matched": _sha256(block) == EVENT_OVERLAY_SHA256,
            "load_destination": "$D800",
        },
        "architecture": (
            "executable mission-control overlay with a Y-indexed indirect "
            "dispatcher; not a serialized opcode stream"
        ),
        "dispatch": [
            {"selector_y": index, "target": "$%04X" % target}
            for index, target in enumerate(dispatch)
        ],
        "module_tables": {
            "A": {
                "cpu": "$%04X" % EVENT_TABLE_A_CPU,
                "record_bytes": 4,
                "records": table_a,
                "selection": (
                    "Y=1 path loads this $371F-indexed module when saved X and "
                    "Y selectors differ"
                ),
            },
            "B": {
                "cpu": "$%04X" % EVENT_TABLE_B_CPU,
                "record_bytes": 4,
                "records": table_b,
                "selection": (
                    "normal mission path indexes this table by $371F and loads "
                    "the selected module to $4000"
                ),
            },
            "C": {
                "cpu": "$%04X" % EVENT_TABLE_C_CPU,
                "record_bytes": 4,
                "records": table_c,
                "selection": (
                    "when interaction result $3709 >= $10, subtract $10, store "
                    "the result in $371F, index this table, and load to $4000"
                ),
            },
        },
        "descriptor_format": {
            "+0": "high CD LBA byte (CL)",
            "+1": "low CD LBA byte (DL)",
            "+2": "middle CD LBA byte (CH)",
            "+3": "CD_READ block count",
        },
        "progress_state": "$371F",
        "exploration_entry": "$4000",
    }


def _decode_adpcm_record(raw: bytes, sample_id: int) -> dict[str, Any]:
    if len(raw) != ADPCM_RECORD_BYTES:
        raise ValueError("ADPCM record must be six bytes")
    return {
        "sample_id": sample_id,
        "raw_hex": raw.hex(),
        "transfer": {
            "cl": raw[0],
            "dl": raw[1],
            "ch": raw[2],
            "block_count": raw[3],
        },
        "playback_length": raw[4] | raw[5] << 8,
        "sample_rate_code": 0x0E,
    }


def _adpcm_report(payload: bytes) -> dict[str, Any]:
    regions = (
        GuardedRegion(
            "adpcm_voice_start",
            ADPCM_MODULE_BASE + ADPCM_START_CPU,
            ADPCM_START_BYTES,
            ADPCM_START_SHA256,
            "Latch active sample ID into $37F1 and execute the voice playback path.",
        ),
        GuardedRegion(
            "adpcm_completion",
            ADPCM_MODULE_BASE + ADPCM_COMPLETION_CPU,
            ADPCM_COMPLETION_BYTES,
            ADPCM_COMPLETION_SHA256,
            "Poll AD_STAT and clear $37F1 when playback becomes idle.",
        ),
        GuardedRegion(
            "adpcm_record_lookup",
            ADPCM_MODULE_BASE + ADPCM_LOOKUP_CPU,
            ADPCM_LOOKUP_BYTES,
            ADPCM_LOOKUP_SHA256,
            "Compute $8BA2 + (sample_id-1)*6 and feed transfer/playback parameters.",
        ),
        GuardedRegion(
            "adpcm_descriptor_table_prefix",
            ADPCM_MODULE_BASE + ADPCM_TABLE_CPU,
            ADPCM_TABLE_BYTES,
            ADPCM_TABLE_SHA256,
            "First 64 proven six-byte voice/sample descriptor records.",
        ),
    )
    table = payload[
        ADPCM_MODULE_BASE + ADPCM_TABLE_CPU :
        ADPCM_MODULE_BASE + ADPCM_TABLE_CPU + ADPCM_TABLE_BYTES
    ]
    records = tuple(
        _decode_adpcm_record(
            table[index * ADPCM_RECORD_BYTES : (index + 1) * ADPCM_RECORD_BYTES],
            index + 1,
        )
        for index in range(ADPCM_PROVEN_RECORDS)
    )
    return {
        "record_bytes": ADPCM_RECORD_BYTES,
        "record_address": "$8BA2 + (sample_id - 1) * 6",
        "active_sample_state": "$37F1",
        "record_format": {
            "+0": "System Card CL transfer-address byte",
            "+1": "System Card DL transfer-address byte",
            "+2": "System Card CH transfer-address byte",
            "+3": "AD_TRANS block count in AL",
            "+4/+5": "little-endian playback length",
        },
        "main_sample_rate_code": "0x0E",
        "regions": tuple(_guard(payload, region) for region in regions),
        "records": records,
    }


def _object_and_interaction_report() -> dict[str, Any]:
    return {
        "object_source_record": {
            "bytes": OBJECT_SOURCE_BYTES,
            "fields": {
                "+0": "animation/type selector",
                "+1": "copied to live +14; no direct exploration-core reader found",
                "+2/+3": "16-bit X position",
                "+4/+5": "16-bit Y position",
                "+6/+7": "copied to live +11/+12; no direct exploration-core reader found",
            },
        },
        "live_object_record": {
            "base": f"${OBJECT_LIVE_BASE:04X}",
            "bytes": OBJECT_LIVE_BYTES,
            "scratch": f"${OBJECT_SCRATCH_BASE:04X}-${OBJECT_SCRATCH_BASE + 15:04X}",
            "fields": {
                "+0/+1": "X position",
                "+2/+3": "Y position",
                "+4/+5/+6": "runtime-reserved/zeroed in this exploration core",
                "+7": "animation countdown",
                "+8/+9": "animation-script pointer",
                "+10": "occupancy-rectangle index",
                "+11/+12": "source auxiliary word; preserved but not read here",
                "+13": "animation/type selector",
                "+14": "source auxiliary byte; preserved but not read here",
                "+15": "reserved; no direct exploration-core reader found",
            },
            "update_model": (
                "each frame copies one 16-byte slot to scratch, advances animation/"
                "render state, then copies the slot back"
            ),
        },
        "interaction_result": {
            "base": f"${INTERACTION_RESULT_BASE:04X}",
            "bytes": INTERACTION_RESULT_BYTES,
            "local_consumers": {
                "+0": "command/type; FF is the proven scene-transition form",
                "+1/+2/+3": (
                    "for FF form, promoted to scene selector, entry selector, and position mode"
                ),
                "+4/+5": (
                    "copied from the interaction record; not read by the exploration "
                    "overlay or startup mission controller"
                ),
                "+6 ($3709)": (
                    "mission-controller result/progress selector: values >= $10 "
                    "become $371F = value-$10 and select module table C"
                ),
                "+7/+8": (
                    "copied from the interaction record; not read by the exploration "
                    "overlay or startup mission controller"
                ),
            },
        },
    }


def build_whole_game_report(path: pathlib.Path) -> dict[str, Any]:
    payload = path.read_bytes()
    digest = sha256_file(path)
    return {
        "scope": "whole-game save, voice, object, interaction, and handoff architecture",
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "save": _save_report(payload),
        "event_control_boundary": {
            "boot_loader": _guard(
                payload,
                GuardedRegion(
                    "boot_event_overlay_loader",
                    BOOT_EVENT_LOADER_OFFSET,
                    BOOT_EVENT_LOADER_BYTES,
                    BOOT_EVENT_LOADER_SHA256,
                    (
                        "Load absolute disc LBA $106F to logical $D800 through "
                        "CD_READ and jump to the mission-control overlay."
                    ),
                ),
            ),
            "controller": _event_control_report(payload),
        },
        "adpcm": _adpcm_report(payload),
        "objects_and_interactions": _object_and_interaction_report(),
        "already_proven_adjacent_systems": {
            "scene_loading": (
                "scene/resource descriptor selection, entry selection, collision/entity/"
                "interaction pointer installation, and CD_READ argument construction are "
                "source-guarded by prove-game-architecture"
            ),
            "graphics": (
                "player meta-sprites, component format, camera/tile refill, text VRAM, "
                "information BAT rectangles, and opening-title planar graphics are "
                "source-guarded by existing proofs"
            ),
        },
        "remaining": {
            "event_control": (
                "the startup $D800 controller is decoded as executable dispatch plus "
                "progress-indexed CD descriptor tables; later mission-specific control "
                "modules can now be compared against this architecture"
            ),
            "binary_ui_assets": (
                "ownership is proven; individual packed schemas should be decoded only "
                "where translation or graphics modification requires them"
            ),
            "live_certification": (
                "later-mission and ENDING MPR/runtime captures remain empirical work"
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate whole-game save/ADPCM/object reverse-engineering evidence."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_whole_game_report(args.payload)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")

    save_ok = all(
        row["write_matches"] and row["read_matches"] and row["file_descriptor_matches"]
        for row in report["save"]["common_copies"]
    ) and all(row["matched"] for row in report["save"]["boot_regions"])
    adpcm_ok = all(row["matched"] for row in report["adpcm"]["regions"])
    event_ok = (
        report["event_control_boundary"]["boot_loader"]["matched"]
        and report["event_control_boundary"]["controller"]["overlay"]["matched"]
    )
    return 0 if report["payload_authenticated"] and save_ok and adpcm_ok and event_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
