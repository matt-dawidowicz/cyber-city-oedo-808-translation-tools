"""Source-backed ADPCM memory-transfer architecture.

Mission 0 does more than stream audio from CD. It temporarily maps one CD-RAM
bank at logical $A000, snapshots 8 KiB of ADPCM RAM into that bank through an
AD_READ-compatible path, and later restores the same 8 KiB with System Card
AD_WRITE ($E039). This explains the short-lived MPR5=$86 mappings in the
historical Mission 0 trace and gives the accelerated build a proven
RAM-to-ADPCM primitive to reuse.

This module records static source evidence only. It does not claim that bank
$87 is free or that Super System Card banks $68-$7F may be passed directly to
AD_WRITE; those are separate runtime/lifetime questions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    payload_offset_for_lba,
)

MISSION0_B_PAYLOAD_BASE = 0x00131800
DIALOGUE_MODULE_PAYLOAD_BASE = payload_offset_for_lba(DIALOGUE_MODULE_LBA)

AD_READ_ENTRY = 0xE036
AD_WRITE_ENTRY = 0xE039

ADPCM_SNAPSHOT_CLEAR_CPU = 0x8394
ADPCM_SNAPSHOT_SAVE_CPU = 0x83C1
ADPCM_SNAPSHOT_RESTORE_CPU = 0x8422
ADPCM_SNAPSHOT_REGION_CPU = 0x8392
ADPCM_SNAPSHOT_REGION_LENGTH = 0xC6
ADPCM_SNAPSHOT_REGION_SHA256 = (
    "3d62ed6e6e41c496fad77efc3ebde4355e74c32b7973ee74fc1611e4ed52fa9a"
)

AD_READ_THUNK_CPU = 0x408E
AD_READ_THUNK_EXPECTED = bytes.fromhex("4C 16 47")
AD_READ_BRIDGE_CPU = 0x4716
AD_READ_BRIDGE_LENGTH = 0x40
AD_READ_BRIDGE_SHA256 = (
    "0911d95a3172f597957a3100f0461b17ed3c2828922b255b0aa899429746e1eb"
)

BANK_MAP_SEQUENCE = bytes.fromhex(
    "43 20 48 AD F5 FF 18 69 06 53 20"
)
ADPCM_TRANSFER_PARAMETERS = bytes.fromhex(
    "A9 00 85 FC "  # CX low
    "A9 E0 85 FD "  # CX high -> ADPCM $E000
    "A9 00 85 FA "  # BX low
    "A9 A0 85 FB "  # BX high -> CPU $A000
    "A9 00 85 F8 "  # AX low
    "A9 20 85 F9 "  # AX high -> $2000 bytes
    "64 FF"         # DH=$00 local memory
)

GENERIC_AD_WRITE_CALL = bytes.fromhex("20 39 E0 60")
EXPECTED_GENERIC_AD_WRITE_WRAPPERS = 92
EXPECTED_GENERIC_AD_WRITE_PAIRS = 46


@dataclass(frozen=True, slots=True)
class GenericAdWriteWrapper:
    payload_offset: int
    adpcm_lo_zp: int
    adpcm_hi_zp: int
    memory_lo_zp: int
    memory_hi_zp: int
    length_lo_zp: int
    length_hi_zp: int
    address_type: int

    @property
    def parameter_zp(self) -> tuple[int, ...]:
        return (
            self.adpcm_lo_zp, self.adpcm_hi_zp,
            self.memory_lo_zp, self.memory_hi_zp,
            self.length_lo_zp, self.length_hi_zp,
        )


def _snapshot_region(payload: bytes) -> bytes:
    start = DIALOGUE_MODULE_PAYLOAD_BASE + ADPCM_SNAPSHOT_REGION_CPU - 0x8000
    return payload[start : start + ADPCM_SNAPSHOT_REGION_LENGTH]


def find_generic_ad_write_wrappers(payload: bytes) -> tuple[GenericAdWriteWrapper, ...]:
    """Find the repeated 32-byte ZP-to-BIOS AD_WRITE wrappers."""

    rows: list[GenericAdWriteWrapper] = []
    cursor = 0
    while True:
        call = payload.find(GENERIC_AD_WRITE_CALL, cursor)
        if call < 0:
            break
        cursor = call + 1
        start = call - 28
        if start < 0:
            continue
        blob = payload[start : call + 4]
        if len(blob) != 32:
            continue
        expected = (
            (0, 0xA5, 2, 0x85, 3, 0xFC),
            (4, 0xA5, 6, 0x85, 7, 0xFD),
            (8, 0xA5, 10, 0x85, 11, 0xFA),
            (12, 0xA5, 14, 0x85, 15, 0xFB),
            (16, 0xA5, 18, 0x85, 19, 0xF8),
            (20, 0xA5, 22, 0x85, 23, 0xF9),
            (24, 0xA9, 26, 0x85, 27, 0xFF),
        )
        if not all(
            blob[a] == av and blob[b] == bv and blob[c] == cv
            for a, av, b, bv, c, cv in expected
        ):
            continue
        rows.append(
            GenericAdWriteWrapper(
                payload_offset=start,
                adpcm_lo_zp=blob[1],
                adpcm_hi_zp=blob[5],
                memory_lo_zp=blob[9],
                memory_hi_zp=blob[13],
                length_lo_zp=blob[17],
                length_hi_zp=blob[21],
                address_type=blob[25],
            )
        )
    return tuple(rows)


def paired_generic_wrappers(
    rows: tuple[GenericAdWriteWrapper, ...],
) -> tuple[tuple[GenericAdWriteWrapper, GenericAdWriteWrapper], ...]:
    """Pair adjacent local/VRAM forms that share the same parameter variables."""

    by_offset = {item.payload_offset: item for item in rows}
    pairs = []
    for left in rows:
        right = by_offset.get(left.payload_offset + 0x20)
        if right is None:
            continue
        if left.parameter_zp != right.parameter_zp:
            continue
        if (left.address_type, right.address_type) != (0x00, 0xFF):
            continue
        pairs.append((left, right))
    return tuple(pairs)


def analyze_adpcm_memory_architecture(payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            f"payload SHA-256 mismatch: expected {TRACK2_PAYLOAD_SHA256}, got {digest}"
        )

    snapshot = _snapshot_region(payload)
    thunk_offset = MISSION0_B_PAYLOAD_BASE + AD_READ_THUNK_CPU
    bridge_offset = MISSION0_B_PAYLOAD_BASE + AD_READ_BRIDGE_CPU
    bridge = payload[bridge_offset : bridge_offset + AD_READ_BRIDGE_LENGTH]
    wrappers = find_generic_ad_write_wrappers(payload)
    pairs = paired_generic_wrappers(wrappers)

    save_relative = ADPCM_SNAPSHOT_SAVE_CPU - ADPCM_SNAPSHOT_REGION_CPU
    restore_relative = ADPCM_SNAPSHOT_RESTORE_CPU - ADPCM_SNAPSHOT_REGION_CPU

    return {
        "snapshot": {
            "module_lba": f"0x{DIALOGUE_MODULE_LBA:04X}",
            "region_cpu": (
                f"$%04X-$%04X" % (
                    ADPCM_SNAPSHOT_REGION_CPU,
                    ADPCM_SNAPSHOT_REGION_CPU + ADPCM_SNAPSHOT_REGION_LENGTH - 1,
                )
            ),
            "region_sha256": hashlib.sha256(snapshot).hexdigest(),
            "region_sha256_match": (
                hashlib.sha256(snapshot).hexdigest() == ADPCM_SNAPSHOT_REGION_SHA256
            ),
            "bank_mapping_sequence_count": snapshot.count(BANK_MAP_SEQUENCE),
            "bank_mapping": (
                "save MPR5; map ($FFF5 max_mapping + 6) into MPR5; restore MPR5"
            ),
            "historical_observed_mapping": "MPR5=$86 during Mission 0 dialogue",
            "adpcm_address": "$E000",
            "cpu_window": "$A000",
            "bytes": 0x2000,
            "save_uses_parameter_block": (
                ADPCM_TRANSFER_PARAMETERS in snapshot[save_relative:]
            ),
            "restore_uses_parameter_block": (
                ADPCM_TRANSFER_PARAMETERS in snapshot[restore_relative:]
            ),
            "restore_calls_ad_write": bytes.fromhex("20 39 E0") in snapshot,
            "state_flag": "$8FF8",
        },
        "ad_read_path": {
            "thunk_cpu": "$408E",
            "thunk_target": "$4716",
            "thunk_source_match": (
                payload[thunk_offset : thunk_offset + 3] == AD_READ_THUNK_EXPECTED
            ),
            "bridge_cpu": "$4716",
            "bridge_sha256_match": (
                hashlib.sha256(bridge).hexdigest() == AD_READ_BRIDGE_SHA256
            ),
            "bios_fallback_present": bytes.fromhex("4C 36 E0") in bridge,
            "meaning": (
                "$408E jumps to a local AD_READ-compatible implementation at $4716; "
                "that bridge falls back to System Card AD_READ $E036 when its "
                "direct-hardware precondition is not met"
            ),
        },
        "generic_ad_write_wrappers": {
            "count": len(wrappers),
            "expected_count": EXPECTED_GENERIC_AD_WRITE_WRAPPERS,
            "mode_00_local": sum(item.address_type == 0x00 for item in wrappers),
            "mode_ff_vram": sum(item.address_type == 0xFF for item in wrappers),
            "adjacent_local_vram_pairs": len(pairs),
            "expected_adjacent_pairs": EXPECTED_GENERIC_AD_WRITE_PAIRS,
            "contract": (
                "CX -> ADPCM address; BX -> memory address; AX -> byte length; "
                "DH -> memory address type"
            ),
        },
        "cache_implication": (
            "Mission 0 already has a proven 8 KiB local-memory-to-ADPCM transfer "
            "through AD_WRITE. A future Super System Card cache can retain source "
            "audio outside ADPCM RAM, stage one 8 KiB block into an owned ordinary "
            "CD-RAM bank, then reuse the existing AD_WRITE contract. Direct "
            "AD_WRITE from Card-RAM banks $68-$7F is not assumed."
        ),
        "release_enabled": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Map Cyber City Oedo 808 RAM/ADPCM transfer architecture."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_adpcm_memory_architecture(args.payload.read_bytes())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    ok = (
        report["snapshot"]["region_sha256_match"]
        and report["snapshot"]["bank_mapping_sequence_count"] >= 2
        and report["snapshot"]["restore_calls_ad_write"]
        and report["ad_read_path"]["thunk_source_match"]
        and report["ad_read_path"]["bridge_sha256_match"]
        and report["ad_read_path"]["bios_fallback_present"]
        and report["generic_ad_write_wrappers"]["count"]
        == EXPECTED_GENERIC_AD_WRITE_WRAPPERS
        and report["generic_ad_write_wrappers"]["adjacent_local_vram_pairs"]
        == EXPECTED_GENERIC_AD_WRITE_PAIRS
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
