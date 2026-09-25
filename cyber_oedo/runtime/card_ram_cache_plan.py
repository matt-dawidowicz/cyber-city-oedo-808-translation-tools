"""Plan a Super System Card cache layout for Mission 0 hot dialogue assets.

This is a static architecture planner. It does not claim that Card RAM banks
$68-$7F are directly consumable by BIOS AD_WRITE or that a particular MPR
mapping is safe at runtime. The purpose is to separate byte-capacity claims
from layouts that are convenient for the game's proven 8 KiB $A000 AD_WRITE
window.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_load_architecture import (
    ADPCM_BLOCK_SECTORS,
    DIALOGUE_MODULE_LENGTH,
    PORTRAIT_TRANSFER_BYTES,
    SPEAKER_BLOCK_COUNT,
    SPEAKER_BLOCK_SECTORS,
)

SECTOR_BYTES = 0x800
CARD_RAM_FIRST_BANK = 0x68
CARD_RAM_LAST_BANK = 0x7F
CARD_RAM_BANK_BYTES = 0x2000
CARD_RAM_BANK_COUNT = CARD_RAM_LAST_BANK - CARD_RAM_FIRST_BANK + 1
CARD_RAM_TOTAL_BYTES = CARD_RAM_BANK_COUNT * CARD_RAM_BANK_BYTES
ACTIVE_ADPCM_BLOCKS = 7


@dataclass(frozen=True, slots=True)
class CacheSlice:
    name: str
    bank: int
    offset: int
    byte_length: int

    @property
    def end_offset_exclusive(self) -> int:
        return self.offset + self.byte_length


def _bank_name(bank: int) -> str:
    return f"$%02X" % bank


def _slice_json(item: CacheSlice) -> dict[str, object]:
    return {
        "name": item.name,
        "bank": _bank_name(item.bank),
        "offset": f"0x{item.offset:04X}",
        "byte_length": item.byte_length,
        "end_offset_exclusive": f"0x{item.end_offset_exclusive:04X}",
    }


def _validate_slice(item: CacheSlice) -> None:
    if not CARD_RAM_FIRST_BANK <= item.bank <= CARD_RAM_LAST_BANK:
        raise ValueError("cache slice bank outside Card RAM range")
    if item.offset < 0 or item.byte_length <= 0:
        raise ValueError("invalid cache slice")
    if item.end_offset_exclusive > CARD_RAM_BANK_BYTES:
        raise ValueError("cache slice crosses an 8 KiB bank")


def build_ad_write_safe_core_layout() -> tuple[CacheSlice, ...]:
    """Lay out core dialogue sources without crossing ADPCM bank boundaries.

    Each 8 KiB ADPCM source gets one dedicated bank so it can be exposed as a
    single logical $A000-$BFFF window. The smaller module/local blocks are
    packed separately without crossing banks.
    """

    rows: list[CacheSlice] = []
    bank = CARD_RAM_FIRST_BANK

    for selector in range(1, ACTIVE_ADPCM_BLOCKS + 1):
        rows.append(
            CacheSlice(
                name=f"speaker_adpcm_{selector}",
                bank=bank,
                offset=0,
                byte_length=ADPCM_BLOCK_SECTORS * SECTOR_BYTES,
            )
        )
        bank += 1

    rows.append(
        CacheSlice(
            name="dialogue_module",
            bank=bank,
            offset=0,
            byte_length=DIALOGUE_MODULE_LENGTH,
        )
    )
    rows.append(
        CacheSlice(
            name="speaker_local_0",
            bank=bank,
            offset=DIALOGUE_MODULE_LENGTH,
            byte_length=SPEAKER_BLOCK_SECTORS * SECTOR_BYTES,
        )
    )
    bank += 1

    local_index = 1
    while local_index < SPEAKER_BLOCK_COUNT:
        rows.append(
            CacheSlice(
                name=f"speaker_local_{local_index}",
                bank=bank,
                offset=0,
                byte_length=SPEAKER_BLOCK_SECTORS * SECTOR_BYTES,
            )
        )
        local_index += 1
        if local_index < SPEAKER_BLOCK_COUNT:
            rows.append(
                CacheSlice(
                    name=f"speaker_local_{local_index}",
                    bank=bank,
                    offset=SPEAKER_BLOCK_SECTORS * SECTOR_BYTES,
                    byte_length=SPEAKER_BLOCK_SECTORS * SECTOR_BYTES,
                )
            )
            local_index += 1
        bank += 1

    for item in rows:
        _validate_slice(item)
    return tuple(rows)


def _banks_used(rows: tuple[CacheSlice, ...]) -> tuple[int, ...]:
    return tuple(sorted({item.bank for item in rows}))


def build_cache_plan() -> dict[str, object]:
    core = build_ad_write_safe_core_layout()
    core_banks = _banks_used(core)
    core_bytes = (
        DIALOGUE_MODULE_LENGTH
        + SPEAKER_BLOCK_COUNT * SPEAKER_BLOCK_SECTORS * SECTOR_BYTES
        + ACTIVE_ADPCM_BLOCKS * ADPCM_BLOCK_SECTORS * SECTOR_BYTES
    )
    raw_core_sector_bytes = (
        46 * SECTOR_BYTES
    )
    portrait_bytes = 2 * PORTRAIT_TRANSFER_BYTES
    packed_lower_bound_bytes = raw_core_sector_bytes + portrait_bytes
    packed_lower_bound_banks = (
        packed_lower_bound_bytes + CARD_RAM_BANK_BYTES - 1
    ) // CARD_RAM_BANK_BYTES

    # With the core kept in an AD_WRITE-friendly 12-bank layout, two 0x2020
    # portraits occupy three additional banks only if the RAM->VRAM copy can be
    # segmented at bank boundaries. Otherwise each portrait needs two banks.
    split_portrait_banks = 3
    independent_portrait_banks = 4

    return {
        "card_ram": {
            "bank_range": "$68-$7F",
            "bank_count": CARD_RAM_BANK_COUNT,
            "bank_bytes": CARD_RAM_BANK_BYTES,
            "total_bytes": CARD_RAM_TOTAL_BYTES,
        },
        "core_source_bytes": {
            "declared_module_and_resources": core_bytes,
            "raw_contiguous_extent_sector_bytes": raw_core_sector_bytes,
            "difference_is_module_sector_tail": raw_core_sector_bytes - core_bytes,
        },
        "capacity_lower_bound": {
            "raw_core_plus_two_portraits_bytes": packed_lower_bound_bytes,
            "banks": packed_lower_bound_banks,
            "meaning": (
                "14 banks is only the byte-capacity lower bound for the raw "
                "46-sector core extent plus two 0x2020 portraits; it does not "
                "by itself provide AD_WRITE-friendly alignment."
            ),
        },
        "ad_write_safe_core": {
            "banks": len(core_banks),
            "bank_range": (
                f"{_bank_name(core_banks[0])}-{_bank_name(core_banks[-1])}"
            ),
            "bytes": core_bytes,
            "capacity_bytes": len(core_banks) * CARD_RAM_BANK_BYTES,
            "slack_bytes": len(core_banks) * CARD_RAM_BANK_BYTES - core_bytes,
            "layout": [_slice_json(item) for item in core],
            "constraint": (
                "every 8 KiB ADPCM source is bank-aligned and contained in one "
                "Card-RAM bank, matching the game's proven one-bank $A000 "
                "local-memory AD_WRITE source window"
            ),
        },
        "two_portrait_extensions": {
            "segmented_copy": {
                "additional_banks": split_portrait_banks,
                "total_banks": len(core_banks) + split_portrait_banks,
                "banks_left": CARD_RAM_BANK_COUNT - len(core_banks) - split_portrait_banks,
                "bytes_left": (
                    CARD_RAM_BANK_COUNT - len(core_banks) - split_portrait_banks
                ) * CARD_RAM_BANK_BYTES,
                "requirement": (
                    "RAM-to-VRAM copy may split a 0x2020 portrait at Card-RAM "
                    "bank boundaries"
                ),
            },
            "independent_two_bank_portraits": {
                "additional_banks": independent_portrait_banks,
                "total_banks": len(core_banks) + independent_portrait_banks,
                "banks_left": (
                    CARD_RAM_BANK_COUNT - len(core_banks) - independent_portrait_banks
                ),
                "bytes_left": (
                    CARD_RAM_BANK_COUNT - len(core_banks) - independent_portrait_banks
                ) * CARD_RAM_BANK_BYTES,
                "requirement": (
                    "each portrait gets its own two-bank allocation; simpler "
                    "ownership, but still requires a split copy because 0x2020 "
                    "bytes exceeds one 8 KiB logical bank"
                ),
            },
        },
        "static_conclusion": (
            "The core cache fits cleanly in 12 Card-RAM banks. A practical bar "
            "working set is 15 banks if portrait copies can be segmented, or 16 "
            "banks with independent two-bank portrait allocations. The previous "
            "14-bank figure remains a capacity lower bound, not the preferred "
            "execution layout."
        ),
        "runtime_gates": [
            "prove Card RAM ownership/lifetime for $68-$7F",
            "prove the chosen MPR mapping while AD_WRITE reads the $A000 window",
            "prove or implement bank-split RAM-to-VRAM portrait copies",
            "do not assume direct optical CD_READ into Card RAM until BIOS behavior is proven",
        ],
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Plan the Mission 0 Super System Card hot-resource cache."
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_cache_plan()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
