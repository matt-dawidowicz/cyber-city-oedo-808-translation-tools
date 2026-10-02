"""Integrated Mission 0 bartender fast-load architecture.

This module turns the independently measured experiments into one explicit,
fail-closed cache lifecycle.  It is deliberately more concrete than the broad
all-Mission cache planner: the allocations below are only for the live Mission 0
bar/bartender route that has runtime evidence.

No release mutation is enabled here.  The purpose is to make bank ownership,
cache validity, preload/fallback behavior, scene snapshotting, and promotion
gates machine-readable before permanent overlay code is emitted.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass

CARD_RAM_BANK_BYTES = 0x2000
CARD_RAM_FIRST_BANK = 0x68
CARD_RAM_LAST_BANK = 0x7F

DIALOGUE_MODULE_BYTES = 0x0F51
BARTENDER_LOCAL_BYTES = 0x1000
PORTRAIT_BYTES = 0x2020
ADPCM_BYTES = 0x2000

SCENE_SPAN_A_BYTES = 0x8E20
SCENE_SPAN_B_BYTES = 0x1A00
SCENE_SNAPSHOT_BYTES = SCENE_SPAN_A_BYTES + SCENE_SPAN_B_BYTES

CACHE_MAGIC = "CCO8FAST"
CACHE_VERSION = 1
METADATA_OFFSET = DIALOGUE_MODULE_BYTES + BARTENDER_LOCAL_BYTES
METADATA_CAPACITY = CARD_RAM_BANK_BYTES - METADATA_OFFSET

STOCK_BUTTON_TO_PARSER_FRAMES = 457
PORTRAIT_ADPCM_BUTTON_TO_PARSER_FRAMES = 336
STOCK_VRAM_RESTORE_FRAMES = 551
SELECTIVE_CD_VRAM_RESTORE_FRAMES = 412


@dataclass(frozen=True, slots=True)
class BankSlice:
    name: str
    first_bank: int
    bank_count: int
    byte_length: int
    role: str

    @property
    def last_bank(self) -> int:
        return self.first_bank + self.bank_count - 1

    @property
    def capacity(self) -> int:
        return self.bank_count * CARD_RAM_BANK_BYTES


BAR_CACHE_LAYOUT = (
    BankSlice("bartender_portrait", 0x68, 2, PORTRAIT_BYTES, "Card RAM -> VDC TIA"),
    BankSlice("adpcm_1292", 0x6A, 1, ADPCM_BYTES, "Card RAM -> ADPCM AD_WRITE"),
    BankSlice("adpcm_1443", 0x6B, 1, ADPCM_BYTES, "Card RAM -> ADPCM AD_WRITE"),
    BankSlice(
        "dialogue_module_plus_bartender_local",
        0x6C,
        1,
        DIALOGUE_MODULE_BYTES + BARTENDER_LOCAL_BYTES,
        "resident fallback source + metadata slack",
    ),
    BankSlice(
        "same_room_scene_snapshot",
        0x6D,
        6,
        SCENE_SNAPSHOT_BYTES,
        "VRAM -> Card RAM snapshot; Card RAM -> VDC restore",
    ),
)


def _bank(bank: int) -> str:
    return f"$%02X" % bank


def build_bar_fast_load_stack() -> dict[str, object]:
    highest_bank = max(item.last_bank for item in BAR_CACHE_LAYOUT)
    allocated_banks = highest_bank - CARD_RAM_FIRST_BANK + 1
    if highest_bank > CARD_RAM_LAST_BANK:
        raise ValueError("bar cache exceeds Super System Card RAM")
    if METADATA_CAPACITY < 0x40:
        raise ValueError("module/local cache leaves insufficient metadata space")

    return {
        "scope": "Mission 0 live bar / bartender route",
        "card_ram": {
            "available_bank_range": "$68-$7F",
            "available_banks": CARD_RAM_LAST_BANK - CARD_RAM_FIRST_BANK + 1,
            "allocated_bank_range": f"{_bank(CARD_RAM_FIRST_BANK)}-{_bank(highest_bank)}",
            "allocated_banks": allocated_banks,
            "banks_remaining": CARD_RAM_LAST_BANK - highest_bank,
            "layout": [
                {
                    "name": item.name,
                    "bank_range": (
                        _bank(item.first_bank)
                        if item.bank_count == 1
                        else f"{_bank(item.first_bank)}-{_bank(item.last_bank)}"
                    ),
                    "banks": item.bank_count,
                    "bytes": item.byte_length,
                    "capacity": item.capacity,
                    "role": item.role,
                }
                for item in BAR_CACHE_LAYOUT
            ],
        },
        "metadata": {
            "bank": "$6C",
            "offset": f"0x{METADATA_OFFSET:04X}",
            "capacity_bytes": METADATA_CAPACITY,
            "magic": CACHE_MAGIC,
            "version": CACHE_VERSION,
            "required_fields": [
                "magic/version",
                "scene id",
                "portrait LBA/tag",
                "two ADPCM LBA/tags",
                "module signature/tag",
                "speaker-local selector/tag",
                "scene-snapshot-valid flag",
            ],
            "policy": "all cache hits fail closed to the stock optical path",
        },
        "fill_lifecycle": [
            {
                "phase": "bar entry / first use",
                "action": (
                    "populate missing route resources into Card RAM through ordinary "
                    "local-memory CD reads, then consume them through the already "
                    "validated TIA/AD_WRITE paths"
                ),
            },
            {
                "phase": "before dialogue clobbers exploration VRAM",
                "action": (
                    "snapshot only the two proven bar restore spans into banks "
                    "$6D-$72 using a VDC-read block-transfer path"
                ),
            },
            {
                "phase": "dialogue entry cache hit",
                "action": (
                    "use resident module only after independent entrypoint/signature "
                    "validation; restore speaker-local/module from $6C on a miss; "
                    "portrait from $68/$69; ADPCM from $6A/$6B"
                ),
            },
            {
                "phase": "dialogue return",
                "action": (
                    "restore the two scene spans from Card RAM rather than issuing "
                    "the stock $22E8 CD-to-VRAM read; if the snapshot tag is invalid, "
                    "fall back to the source-guarded two-span CD restore"
                ),
            },
            {
                "phase": "scene/mission change or save-state uncertainty",
                "action": "invalidate route tags; never trust stale Card RAM",
            },
        ],
        "measured_evidence": {
            "stock_button_to_parser_frames": STOCK_BUTTON_TO_PARSER_FRAMES,
            "portrait_plus_adpcm_button_to_parser_frames": (
                PORTRAIT_ADPCM_BUTTON_TO_PARSER_FRAMES
            ),
            "entry_frames_saved": (
                STOCK_BUTTON_TO_PARSER_FRAMES - PORTRAIT_ADPCM_BUTTON_TO_PARSER_FRAMES
            ),
            "entry_seconds_saved": (
                STOCK_BUTTON_TO_PARSER_FRAMES - PORTRAIT_ADPCM_BUTTON_TO_PARSER_FRAMES
            )
            / 60.0,
            "stock_vram_restore_frames": STOCK_VRAM_RESTORE_FRAMES,
            "selective_cd_vram_restore_frames": SELECTIVE_CD_VRAM_RESTORE_FRAMES,
            "selective_cd_frames_saved": (
                STOCK_VRAM_RESTORE_FRAMES - SELECTIVE_CD_VRAM_RESTORE_FRAMES
            ),
            "card_ram_scene_restore": (
                "mechanism designed but not yet assigned a measured frame count; "
                "do not substitute a theoretical TIA duration"
            ),
        },
        "promotion_gates": [
            "prove Card-RAM contents survive the complete bar/dialogue round trip",
            "prove VRAM->Card-RAM snapshot path byte-for-byte against pre-dialogue VRAM",
            "prove Card-RAM->VRAM return image byte-for-byte against stock return",
            "run combined module/speaker/portrait/ADPCM cache timing in one build",
            "classify the $7B7C setup VSync gate before shortening it",
            "validate fast audio teardown with subsequent voice/CD-DA playback",
            "repeat dirty-range/cache validation for every room/NPC before generalizing",
        ],
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Describe the integrated bar fast-load stack.")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_bar_fast_load_stack()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
