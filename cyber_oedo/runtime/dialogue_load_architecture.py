"""Source-guarded Mission 0 dialogue-load architecture.

This module describes the exact on-disc layout used by the repeatedly observed
Mission 0 portrait/dialogue transition.  It exists to support load-time
optimization without treating arbitrary fill bytes as free space.

Important findings:

* the common dialogue module is exactly 0x0F51 bytes from LBA 0x1425;
* its generic byte loader reads one full sector plus one remainder sector;
* only 0x0751 bytes of sector 0x1426 belong to the declared module, leaving an
  authenticated 0x00-filled 0x00AF-byte source tail outside that length;
* the module contains two eight-entry three-byte source tables: 2-sector
  speaker/UI blocks and 4-sector ADPCM blocks;
* for active indices 1..7 the 4-sector ADPCM block begins immediately after the
  corresponding 2-sector block;
* Mission 0 also contains 135 consecutive five-sector portrait slots.  The
  observed portrait transfer length is 0x2020 bytes, so each slot's fifth
  sector contains only 0x20 transferred bytes and 0x7E0 bytes outside that
  transfer length.

The source tails are optimization candidates, not automatically writable
ownership.  Mutation still requires proving that no other consumer owns them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256

SECTOR_BYTES = 0x800
TRACK2_START_LBA = 3590
MISSION0_B_PAYLOAD_BASE = 0x00131800

DIALOGUE_MODULE_LBA = 0x1425
DIALOGUE_MODULE_LENGTH = 0x0F51
DIALOGUE_MODULE_SHA256 = (
    "20d414eb643dd66990abe381881082308b30bbc9ae465622676a132377f16636"
)
DIALOGUE_MODULE_CPU = 0x8000
DIALOGUE_MODULE_LOADER_CPU = 0x48AE
DIALOGUE_MODULE_LOADER_BYTES = bytes.fromhex(
    "A9 00 85 00 A9 80 85 01 A9 00 85 02 "
    "A9 25 85 04 A9 14 85 05 A9 51 85 06 "
    "A9 0F 85 07 20 A0 6E 68 53 10 60"
)

MODULE_SOURCE_TABLE_RELATIVE = 0x0B73
MODULE_SOURCE_TABLE_SHA256 = (
    "7bff08717641bdefb59a2fab24be3b284556e7debaf449b7085ba7a62ee0e9f4"
)
SPEAKER_BLOCK_COUNT = 8
SPEAKER_BLOCK_SECTORS = 2
ADPCM_BLOCK_SECTORS = 4

PORTRAIT_TABLE_CPU = 0x605C
PORTRAIT_SLOT_COUNT = 135
PORTRAIT_SLOT_SECTORS = 5
PORTRAIT_TRANSFER_BYTES = 0x2020
PORTRAIT_TABLE_SHA256 = (
    "5427808b61997268ac0af4b8f9405d4f1627697c725e2666b38061c5b6470cde"
)


@dataclass(frozen=True, slots=True)
class SpeakerLoadPair:
    index: int
    local_lba: int
    adpcm_lba: int
    adpcm_used: bool

    @property
    def local_end_lba_exclusive(self) -> int:
        return self.local_lba + SPEAKER_BLOCK_SECTORS

    @property
    def contiguous(self) -> bool:
        return self.adpcm_lba == self.local_end_lba_exclusive


@dataclass(frozen=True, slots=True)
class PortraitSlot:
    index: int
    lba: int
    sectors: int

    @property
    def allocated_bytes(self) -> int:
        return self.sectors * SECTOR_BYTES

    @property
    def untransferred_tail_bytes(self) -> int:
        return self.allocated_bytes - PORTRAIT_TRANSFER_BYTES


def payload_offset_for_lba(lba: int) -> int:
    relative = lba - TRACK2_START_LBA
    if relative < 0:
        raise ValueError("LBA precedes Track 2")
    return relative * SECTOR_BYTES


def _decode_game_lba(raw: bytes) -> int:
    """Decode the game's [high, low, middle] three-byte LBA representation."""

    if len(raw) != 3:
        raise ValueError("game LBA entry must be exactly three bytes")
    return (raw[0] << 16) | (raw[2] << 8) | raw[1]


def validate_dialogue_module(payload: bytes) -> dict[str, bool]:
    module_offset = payload_offset_for_lba(DIALOGUE_MODULE_LBA)
    module = payload[module_offset : module_offset + DIALOGUE_MODULE_LENGTH]
    loader_offset = MISSION0_B_PAYLOAD_BASE + DIALOGUE_MODULE_LOADER_CPU
    loader = payload[
        loader_offset : loader_offset + len(DIALOGUE_MODULE_LOADER_BYTES)
    ]
    table = module[
        MODULE_SOURCE_TABLE_RELATIVE : MODULE_SOURCE_TABLE_RELATIVE + 16 * 3
    ]

    second_sector = payload[
        payload_offset_for_lba(DIALOGUE_MODULE_LBA + 1) :
        payload_offset_for_lba(DIALOGUE_MODULE_LBA + 2)
    ]
    declared_second_sector_bytes = DIALOGUE_MODULE_LENGTH - SECTOR_BYTES
    tail = second_sector[declared_second_sector_bytes:]

    return {
        "module_sha256": hashlib.sha256(module).hexdigest()
        == DIALOGUE_MODULE_SHA256,
        "loader_bytes": loader == DIALOGUE_MODULE_LOADER_BYTES,
        "source_table_sha256": hashlib.sha256(table).hexdigest()
        == MODULE_SOURCE_TABLE_SHA256,
        "second_sector_tail_length": len(tail) == 0x00AF,
        "second_sector_tail_zero": tail == bytes(0x00AF),
    }


def speaker_load_pairs(payload: bytes) -> tuple[SpeakerLoadPair, ...]:
    checks = validate_dialogue_module(payload)
    if not all(checks.values()):
        raise ValueError(f"dialogue module source guard mismatch: {checks}")

    module_offset = payload_offset_for_lba(DIALOGUE_MODULE_LBA)
    table_offset = module_offset + MODULE_SOURCE_TABLE_RELATIVE
    table = payload[table_offset : table_offset + 16 * 3]

    local = tuple(
        _decode_game_lba(table[index * 3 : index * 3 + 3])
        for index in range(SPEAKER_BLOCK_COUNT)
    )
    adpcm_base = SPEAKER_BLOCK_COUNT * 3
    adpcm = tuple(
        _decode_game_lba(
            table[
                adpcm_base + index * 3 :
                adpcm_base + index * 3 + 3
            ]
        )
        for index in range(SPEAKER_BLOCK_COUNT)
    )

    return tuple(
        SpeakerLoadPair(
            index=index,
            local_lba=local[index],
            adpcm_lba=adpcm[index],
            # Module $80BB skips AD_TRANS when index == 0.
            adpcm_used=index != 0,
        )
        for index in range(SPEAKER_BLOCK_COUNT)
    )


def portrait_slots(payload: bytes) -> tuple[PortraitSlot, ...]:
    table_offset = MISSION0_B_PAYLOAD_BASE + PORTRAIT_TABLE_CPU
    byte_count = PORTRAIT_SLOT_COUNT * 4
    table = payload[table_offset : table_offset + byte_count]
    if hashlib.sha256(table).hexdigest() != PORTRAIT_TABLE_SHA256:
        raise ValueError("Mission 0 portrait table source guard mismatch")

    result = []
    for index in range(PORTRAIT_SLOT_COUNT):
        entry = table[index * 4 : index * 4 + 4]
        lba = entry[0] | (entry[1] << 8) | (entry[3] << 16)
        sectors = entry[2]
        result.append(PortraitSlot(index=index, lba=lba, sectors=sectors))
    return tuple(result)


def analyze_dialogue_load_architecture(payload: bytes) -> dict[str, object]:
    payload_hash = hashlib.sha256(payload).hexdigest()
    if payload_hash != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            "payload SHA-256 mismatch: "
            f"expected {TRACK2_PAYLOAD_SHA256}, got {payload_hash}"
        )

    checks = validate_dialogue_module(payload)
    if not all(checks.values()):
        raise ValueError(f"dialogue module source guard mismatch: {checks}")

    pairs = speaker_load_pairs(payload)
    portraits = portrait_slots(payload)
    active_pairs = tuple(item for item in pairs if item.adpcm_used)

    return {
        "dialogue_module": {
            "absolute_lba": f"0x{DIALOGUE_MODULE_LBA:04X}",
            "byte_length": DIALOGUE_MODULE_LENGTH,
            "sectors_touched": 2,
            "second_sector_declared_bytes": DIALOGUE_MODULE_LENGTH - SECTOR_BYTES,
            "second_sector_unowned_candidate_tail_bytes": (
                2 * SECTOR_BYTES - DIALOGUE_MODULE_LENGTH
            ),
            "source_guards": checks,
        },
        "speaker_pairs": [
            {
                "index": item.index,
                "local_lba": f"0x{item.local_lba:04X}",
                "local_sectors": SPEAKER_BLOCK_SECTORS,
                "adpcm_lba": f"0x{item.adpcm_lba:04X}",
                "adpcm_sectors": ADPCM_BLOCK_SECTORS if item.adpcm_used else 0,
                "adpcm_used": item.adpcm_used,
                "contiguous": item.contiguous,
            }
            for item in pairs
        ],
        "active_speaker_pairs_contiguous": all(
            item.contiguous for item in active_pairs
        ),
        "core_dialogue_extent": {
            "start_lba": "0x1425",
            "end_lba_inclusive": "0x1452",
            "sectors": 0x1452 - 0x1425 + 1,
            "bytes": (0x1452 - 0x1425 + 1) * SECTOR_BYTES,
            "fits_in_super_cd_192k": (
                (0x1452 - 0x1425 + 1) * SECTOR_BYTES <= 192 * 1024
            ),
        },
        "portrait_table": {
            "slots": len(portraits),
            "first_lba": f"0x{portraits[0].lba:04X}",
            "last_lba": f"0x{portraits[-1].lba:04X}",
            "slot_sectors": PORTRAIT_SLOT_SECTORS,
            "transfer_bytes_per_portrait": PORTRAIT_TRANSFER_BYTES,
            "untransferred_tail_bytes_per_slot": portraits[0].untransferred_tail_bytes,
            "total_untransferred_tail_bytes": sum(
                item.untransferred_tail_bytes for item in portraits
            ),
            "five_sector_stride": all(
                right.lba == left.lba + PORTRAIT_SLOT_SECTORS
                for left, right in zip(portraits, portraits[1:])
            ),
        },
        "optimization_implication": (
            "The invariant module plus all active 2-sector/4-sector speaker "
            "bundles occupy one 46-sector contiguous extent (0x1425-0x1452), "
            "94,208 bytes total. A System Card 3.0-only cache can therefore "
            "potentially prefetch the entire core dialogue/audio source set "
            "into the 192 KiB Super CD work RAM and replace repeated optical "
            "reads with RAM copies / AD_WRITE operations. Runtime ownership "
            "and BIOS cross-bank transfer behavior still require live proof."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Map the authenticated Mission 0 dialogue, ADPCM, and portrait "
            "load layout used by the slow interaction transitions."
        )
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = analyze_dialogue_load_architecture(args.payload.read_bytes())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
