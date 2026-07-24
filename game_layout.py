#!/usr/bin/env python3
"""Confirmed disc-layout constants shared by the analysis tools.

This module is the single source of truth for facts that were established from
the supplied CloneCD image.  Keeping these values out of individual scanners
prevents subtle disagreements about sector size, bank boundaries, or record
markers.

Coordinate systems used throughout the toolkit
-----------------------------------------------

``absolute LBA``
    A sector number in the complete CloneCD image.  Track 2 INDEX 01 begins at
    absolute LBA 3590.

``relative sector``
    A 2048-byte user-data sector in ``track02_mode1_2048.bin``.  Relative
    sector zero is absolute LBA 3590.

``payload offset``
    A byte offset in ``track02_mode1_2048.bin``.  It is always calculated as
    ``relative_sector * 2048 + within_sector``.

The mission ranges below are analysis regions, not a claim about a filesystem.
The disc is directoryless.  Their boundaries are repeated engine/resource
anchors observed in the extracted payload.

Do not add guessed control-byte meanings here.  ``COMMON_DIALOGUE_CONTROLS``
only records which values are common enough to pass the extraction heuristic;
their runtime semantics still require emulator tracing.
"""

from __future__ import annotations

from dataclasses import dataclass


# Raw CloneCD sectors are 2352 bytes.  The extracted Mode 1 user-data sectors
# consumed by every other tool are 2048 bytes.
RAW_SECTOR_SIZE = 2352
MODE1_USER_DATA_OFFSET = 16
SECTOR_SIZE = 2048

# Title-specific Track 2 geometry established from the supplied CCD/IMG pair.
TRACK2_START_LBA = 3590
TRACK2_SECTOR_COUNT = 41199
TRACK2_END_LBA_EXCLUSIVE = TRACK2_START_LBA + TRACK2_SECTOR_COUNT

# Dialogue records observed in the data begin with this two-byte bytecode and
# terminate with 00.  The marker is included in record offsets and byte counts.
DIALOGUE_MARKER = b"\x27\x28"

# These bytes are preserved as opaque controls in tagged text.  The names of
# their actions are deliberately not guessed.
COMMON_DIALOGUE_CONTROLS = frozenset({0x21, 0x2F, 0x40, 0x5C})

# Constant-fill bytes commonly seen after resource data.  Seeing one of these
# does not prove that the area is safe for relocation.
LIKELY_PADDING_BYTES = frozenset({0x00, 0x08, 0xE5, 0xFF})


@dataclass(frozen=True, slots=True)
class BankRange:
    """A half-open range of relative sectors used for inventory grouping."""

    name: str
    start_sector: int
    end_sector: int

    def contains_sector(self, sector: int) -> bool:
        """Return whether *sector* falls in ``[start_sector, end_sector)``."""

        return self.start_sector <= sector < self.end_sector


BANKS: tuple[BankRange, ...] = (
    BankRange("MISSION_0", 0, 5376),
    BankRange("MISSION_1", 5376, 11047),
    BankRange("MISSION_2", 11047, 16554),
    BankRange("MISSION_3", 16554, 20924),
    BankRange("MISSION_4", 20924, 25371),
    BankRange("MISSION_5", 25371, 29334),
    BankRange("MISSION_6", 29334, 32831),
    BankRange("MISSION_7", 32831, 36132),
    BankRange("MISSION_8", 36132, 39435),
    BankRange("ENDING", 39435, TRACK2_SECTOR_COUNT),
)


def bank_for_sector(sector: int) -> str:
    """Map a relative Track 2 sector to its analysis bank name.

    ``BOOT`` is returned for an out-of-range value.  The name is historical:
    callers normally encounter it only when scanning malformed or unrelated
    input, because ``MISSION_0`` begins at sector zero.
    """

    for bank in BANKS:
        if bank.contains_sector(sector):
            return bank.name
    return "BOOT"


def bank_for_offset(offset: int) -> str:
    """Map a byte offset in the extracted payload to an analysis bank."""

    return bank_for_sector(offset // SECTOR_SIZE)


def payload_offset(sector: int, within_sector: int = 0) -> int:
    """Convert a relative sector and in-sector offset to a payload byte offset."""

    if sector < 0:
        raise ValueError("sector must be non-negative")
    if not 0 <= within_sector < SECTOR_SIZE:
        raise ValueError(f"within_sector must be in the range 0..{SECTOR_SIZE - 1}")
    return sector * SECTOR_SIZE + within_sector


def absolute_lba(relative_sector: int) -> int:
    """Convert a relative Track 2 sector number to an absolute CloneCD LBA."""

    return TRACK2_START_LBA + relative_sector
