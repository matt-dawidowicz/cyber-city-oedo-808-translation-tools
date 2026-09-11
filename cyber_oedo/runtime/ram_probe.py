"""Classify HuC6280 MPR snapshots for the B3 English-RAM investigation.

This module is deliberately read-only.  Hardware RAM that is absent from one
MPR snapshot is a probe candidate, never proof of ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MPR_COUNT = 8
LOGICAL_PAGE_SIZE = 0x2000
CD_RAM_BANKS = frozenset(range(0x80, 0x88))
SYSTEM_CARD_3_RAM_BANKS = frozenset(range(0x68, 0x80))
LIVE_H_BARTEN_BANKS = frozenset(range(0x80, 0x85))
B3_RAM_CANDIDATES = frozenset(
    (CD_RAM_BANKS - LIVE_H_BARTEN_BANKS) | SYSTEM_CARD_3_RAM_BANKS
)


@dataclass(frozen=True, slots=True)
class MprMapping:
    """Describe one logical 8 KiB page mapped to one physical bank."""

    mpr: int
    physical_bank: int

    def __post_init__(self) -> None:
        if not 0 <= self.mpr < MPR_COUNT:
            raise ValueError("MPR index must lie between 0 and 7")
        if not 0 <= self.physical_bank <= 0xFF:
            raise ValueError("physical bank must fit in one byte")

    @property
    def logical_start(self) -> int:
        """Return the first logical CPU address controlled by this MPR."""

        return self.mpr * LOGICAL_PAGE_SIZE

    @property
    def logical_end(self) -> int:
        """Return the inclusive final logical CPU address for this MPR."""

        return self.logical_start + LOGICAL_PAGE_SIZE - 1


@dataclass(frozen=True, slots=True)
class MprSnapshot:
    """Store one labeled debugger snapshot of all eight HuC6280 MPRs."""

    label: str
    pc: int
    mprs: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("snapshot label must not be empty")
        if not 0 <= self.pc <= 0xFFFF:
            raise ValueError("program counter must fit in 16 bits")
        if len(self.mprs) != MPR_COUNT:
            raise ValueError("snapshot must contain exactly eight MPR values")
        if any(not 0 <= bank <= 0xFF for bank in self.mprs):
            raise ValueError("every MPR value must fit in one byte")

    def mappings(self) -> tuple[MprMapping, ...]:
        """Return logical-to-physical mappings in MPR order."""

        return tuple(
            MprMapping(mpr=index, physical_bank=bank)
            for index, bank in enumerate(self.mprs)
        )


def candidate_mappings(snapshot: MprSnapshot) -> tuple[MprMapping, ...]:
    """Return mappings that touch a B3 RAM candidate bank."""

    return tuple(
        mapping
        for mapping in snapshot.mappings()
        if mapping.physical_bank in B3_RAM_CANDIDATES
    )


def summarize_candidate_usage(
    snapshots: tuple[MprSnapshot, ...],
) -> dict[str, Any]:
    """Summarize sampled candidate mappings without promoting unused RAM.

    A bank reported as ``not_mapped_in_sample`` is still unproven.  System Card
    or game code may touch it outside the sampled anchors or through a transient
    mapping that was not captured.
    """

    if not snapshots:
        raise ValueError("at least one MPR snapshot is required")

    seen: dict[int, list[dict[str, Any]]] = {
        bank: [] for bank in sorted(B3_RAM_CANDIDATES)
    }
    for snapshot in snapshots:
        for mapping in candidate_mappings(snapshot):
            seen[mapping.physical_bank].append(
                {
                    "label": snapshot.label,
                    "pc": f"0x{snapshot.pc:04X}",
                    "mpr": mapping.mpr,
                    "logical_start": f"0x{mapping.logical_start:04X}",
                    "logical_end": f"0x{mapping.logical_end:04X}",
                }
            )

    return {
        "ownership_conclusion": "no candidate is promoted by MPR sampling alone",
        "banks": [
            {
                "physical_bank": f"0x{bank:02X}",
                "hardware_pool": (
                    "cd_ram" if bank in CD_RAM_BANKS else "system_card_3_ram"
                ),
                "sample_status": (
                    "mapped_in_sample" if observations else "not_mapped_in_sample"
                ),
                "observations": observations,
            }
            for bank, observations in seen.items()
        ],
    }


__all__ = [
    "B3_RAM_CANDIDATES",
    "CD_RAM_BANKS",
    "LIVE_H_BARTEN_BANKS",
    "LOGICAL_PAGE_SIZE",
    "MPR_COUNT",
    "MprMapping",
    "MprSnapshot",
    "SYSTEM_CARD_3_RAM_BANKS",
    "candidate_mappings",
    "summarize_candidate_usage",
]
