"""Map logical address overlap between dialogue and exploration resources.

Logical overlap is not physical CD-RAM ownership proof on the HuC6280 because
MPR mappings may change between overlays. This module intentionally reports
that distinction instead of treating matching CPU addresses as bank identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from cyber_oedo.analysis.disassemble_huc6280 import linear_disassemble
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.game_architecture import MOVEMENT_ARCHITECTURE_REGIONS
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_residency import (
    MODULE_CPU_END_EXCLUSIVE,
    MODULE_CPU_START,
    SPEAKER_LOCAL_END_EXCLUSIVE,
    SPEAKER_LOCAL_START,
)

SECTOR_BYTES = 0x800
MPR_WINDOW_BYTES = 0x2000
DIALOGUE_PHYSICAL_PAGE = 0x85


@dataclass(frozen=True, slots=True)
class AddressRange:
    name: str
    start: int
    end_exclusive: int
    domain: str

    @property
    def bytes(self) -> int:
        return self.end_exclusive - self.start


DIALOGUE_MODULE = AddressRange(
    "dialogue_module",
    MODULE_CPU_START,
    MODULE_CPU_END_EXCLUSIVE,
    "cpu_logical",
)
DIALOGUE_SPEAKER = AddressRange(
    "dialogue_speaker_local",
    SPEAKER_LOCAL_START,
    SPEAKER_LOCAL_END_EXCLUSIVE,
    "cpu_logical",
)
EXPLORATION_LOCAL_A = AddressRange(
    "exploration_scene_local_a",
    0x4000,
    0x4000 + 7 * SECTOR_BYTES,
    "cpu_logical",
)
EXPLORATION_LOCAL_B = AddressRange(
    "exploration_scene_local_b",
    0x9000,
    0x9000 + 3 * SECTOR_BYTES,
    "cpu_logical",
)


def overlap(left: AddressRange, right: AddressRange) -> AddressRange | None:
    if left.domain != right.domain:
        return None
    start = max(left.start, right.start)
    end = min(left.end_exclusive, right.end_exclusive)
    if start >= end:
        return None
    return AddressRange(
        f"{left.name}_x_{right.name}",
        start,
        end,
        left.domain,
    )


def logical_page_geometry(start: int, end_exclusive: int) -> tuple[dict[str, object], ...]:
    """Split a logical range at HuC6280 8 KiB MPR-window boundaries."""

    rows: list[dict[str, object]] = []
    cursor = start
    while cursor < end_exclusive:
        slot = cursor // MPR_WINDOW_BYTES
        slot_end = (slot + 1) * MPR_WINDOW_BYTES
        end = min(end_exclusive, slot_end)
        rows.append(
            {
                "mpr_slot": slot,
                "logical_start": f"$%04X" % cursor,
                "logical_end_inclusive": f"$%04X" % (end - 1),
                "page_offset_start": f"0x{cursor & (MPR_WINDOW_BYTES - 1):04X}",
                "page_offset_end_inclusive": f"0x{(end - 1) & (MPR_WINDOW_BYTES - 1):04X}",
                "bytes": end - cursor,
            }
        )
        cursor = end
    return tuple(rows)


def _range_json(item: AddressRange) -> dict[str, object]:
    return {
        "name": item.name,
        "start": f"$%04X" % item.start,
        "end_inclusive": f"$%04X" % (item.end_exclusive - 1),
        "bytes": item.bytes,
        "domain": item.domain,
    }


def _architecture_region(name: str):
    return next(item for item in MOVEMENT_ARCHITECTURE_REGIONS if item.name == name)


def analyze_scene_mpr_operations(payload: bytes) -> dict[str, object]:
    """Decode MPR4/MPR5 operations in authenticated scene-transition code."""

    digest = hashlib.sha256(payload).hexdigest()
    if digest != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            f"payload SHA-256 mismatch: expected {TRACK2_PAYLOAD_SHA256}, got {digest}"
        )

    regions = (
        _architecture_region("scene_and_room_setup"),
        _architecture_region("scene_cd_loaders"),
    )
    rows: list[dict[str, object]] = []
    for region in regions:
        blob = payload[region.payload_offset : region.payload_offset + region.length]
        if hashlib.sha256(blob).hexdigest() != region.sha256:
            raise ValueError(f"source guard mismatch for {region.name}")
        previous = None
        for instruction in linear_disassemble(
            blob, region.payload_offset, region.cpu_start
        ):
            if instruction.mnemonic in {"tam", "tma"} and instruction.raw[1] & 0x30:
                mprs = []
                if instruction.raw[1] & 0x10:
                    mprs.append("MPR4")
                if instruction.raw[1] & 0x20:
                    mprs.append("MPR5")
                immediate = None
                if (
                    previous is not None
                    and previous.mnemonic == "lda"
                    and previous.raw[0] == 0xA9
                    and instruction.mnemonic == "tam"
                ):
                    immediate = f"$%02X" % previous.raw[1]
                rows.append(
                    {
                        "region": region.name,
                        "cpu": f"$%04X" % instruction.cpu_address,
                        "operation": instruction.mnemonic.upper(),
                        "mask": f"$%02X" % instruction.raw[1],
                        "mprs": mprs,
                        "immediate_accumulator_if_adjacent": immediate,
                        "instruction": instruction.format(),
                    }
                )
            previous = instruction

    mpr4_writes = [
        row for row in rows
        if row["operation"] == "TAM" and "MPR4" in row["mprs"]
    ]
    immediate_values = {
        row["immediate_accumulator_if_adjacent"]
        for row in mpr4_writes
        if row["immediate_accumulator_if_adjacent"] is not None
    }
    resolved = (
        len(mpr4_writes) > 0
        and len(immediate_values) == 1
        and all(
            row["immediate_accumulator_if_adjacent"] is not None
            for row in mpr4_writes
        )
    )
    return {
        "operations": rows,
        "mpr4_write_count": len(mpr4_writes),
        "adjacent_immediate_mpr4_values": sorted(immediate_values),
        "mpr4_statically_resolved": resolved,
        "resolved_mpr4": next(iter(immediate_values)) if resolved else None,
        "interpretation": (
            "Only instruction-boundary-decoded TAM/TMA operations in the "
            "source-guarded scene setup/loader regions are reported. An MPR4 "
            "value is declared statically resolved only when every MPR4 TAM in "
            "those regions is immediately preceded by one identical LDA #imm. "
            "Otherwise runtime MPR capture remains required."
        ),
    }

def build_resource_lifetime_report() -> dict[str, object]:
    module_overlap = overlap(DIALOGUE_MODULE, EXPLORATION_LOCAL_B)
    speaker_overlap = overlap(DIALOGUE_SPEAKER, EXPLORATION_LOCAL_B)
    return {
        "ranges": {
            item.name: _range_json(item)
            for item in (
                DIALOGUE_MODULE,
                DIALOGUE_SPEAKER,
                EXPLORATION_LOCAL_A,
                EXPLORATION_LOCAL_B,
            )
        },
        "known_exploration_logical_overlap": {
            "dialogue_module_vs_local_b": (
                None if module_overlap is None else _range_json(module_overlap)
            ),
            "speaker_local_vs_local_b": (
                None if speaker_overlap is None else _range_json(speaker_overlap)
            ),
            "speaker_window_fully_covered": (
                speaker_overlap is not None
                and speaker_overlap.start == DIALOGUE_SPEAKER.start
                and speaker_overlap.end_exclusive == DIALOGUE_SPEAKER.end_exclusive
            ),
        },
        "mpr_geometry": {
            "window_bytes": MPR_WINDOW_BYTES,
            "dialogue_workspace_mpr_slot": 4,
            "dialogue_known_physical_page": "$%02X" % DIALOGUE_PHYSICAL_PAGE,
            "module_page_offsets": ["0x0000", "0x0F50"],
            "speaker_page_offsets": ["0x1000", "0x1FFF"],
            "exploration_local_b_segments": list(
                logical_page_geometry(
                    EXPLORATION_LOCAL_B.start,
                    EXPLORATION_LOCAL_B.end_exclusive,
                )
            ),
            "same_page_hypothesis": (
                "If exploration MPR4 remains $85, the $9000-$9FFF half of the "
                "$22DE load overwrites exactly the speaker-local half of page $85 "
                "while leaving the module at page offsets 0x0000-0x0F50 intact. "
                "The remaining $A000-$A7FF portion is in MPR5 and cannot touch "
                "the page-$85 speaker bytes."
            ),
            "remapped_page_hypothesis": (
                "If exploration MPR4 is not $85, the logical $9000-$9FFF write "
                "targets a different physical 8 KiB page and page $85 survives "
                "unchanged. Static logical addresses alone cannot choose between "
                "these two cases."
            ),
            "proof_needed": (
                "MPR4 at the exploration $22DE CD_READ and MPR4 at dialogue "
                "speaker-local use, or an equivalent physical-CD-RAM checksum."
            ),
        },
        "static_implication": (
            "Known exploration scene-local writes do not overlap the dialogue "
            "module's logical $8000-$8F50 body, but the 3-sector $9000 load "
            "covers the entire logical $9000-$9FFF speaker-local window and "
            "continues through $A7FF."
        ),
        "mpr_caveat": (
            "Logical $9000 is in MPR4 and $A000 begins MPR5. Dialogue page $85 "
            "places the module in offsets 0x0000-0x0F50 and speaker-local data in "
            "0x1000-0x1FFF. The exploration write therefore has a precise "
            "conditional consequence: speaker clobber occurs if and only if its "
            "MPR4 maps the same physical page $85. Static evidence has not yet "
            "proven that exploration MPR4 value."
        ),
        "optimization_priority": (
            "Keep resident-module and speaker-cache benchmarks independent. "
            "Static overlap makes the speaker-local cache the higher-risk "
            "lifetime assumption; module residency has no equivalent known "
            "logical scene-write overlap."
        ),
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map logical resource overlap across dialogue/exploration."
    )
    parser.add_argument(
        "--payload",
        type=pathlib.Path,
        help="authenticated Track 2 payload for instruction-boundary MPR analysis",
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_resource_lifetime_report()
    if args.payload is not None:
        report["scene_mpr_operations"] = analyze_scene_mpr_operations(
            args.payload.read_bytes()
        )
    else:
        report["scene_mpr_operations"] = {
            "status": "not_run",
            "reason": "supply --payload to decode authenticated TAM/TMA operations",
        }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
