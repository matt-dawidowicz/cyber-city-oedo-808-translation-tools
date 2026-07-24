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


# Raw CloneCD sectors are 2352 bytes. The extracted Mode 1 user-data
# sectors consumed by every other tool are 2048 bytes.
RAW_SECTOR_SIZE = 2352
MODE1_USER_DATA_OFFSET = 16
SECTOR_SIZE = 2048

# These title-specific values were established from the supplied CCD/IMG
# pair. They are not defaults for arbitrary PC Engine CD images.
TRACK2_START_LBA = 3590
TRACK2_SECTOR_COUNT = 41199
TRACK2_END_LBA_EXCLUSIVE = TRACK2_START_LBA + TRACK2_SECTOR_COUNT

# Observed dialogue records begin with this two-byte bytecode and end with
# 00. Record offsets and byte counts include both marker and terminator.
DIALOGUE_MARKER = b"\x27\x28"

# These bytes are preserved as opaque controls in tagged text. Their
# runtime actions are deliberately not guessed.
COMMON_DIALOGUE_CONTROLS = frozenset({0x21, 0x2F, 0x40, 0x5C})

# These constant-fill bytes commonly follow resource data. Their presence
# does not prove that a region is safe for relocation.
LIKELY_PADDING_BYTES = frozenset({0x00, 0x08, 0xE5, 0xFF})


@dataclass(frozen=True, slots=True)
class BankRange:
    """Represent a half-open Track 2 range used for inventory grouping.

    The range is expressed in relative 2048-byte payload sectors. It is an
    analysis label derived from repeated engine anchors, not a filesystem
    partition or a guarantee about runtime loading.

    Attributes:
        name: Stable label written to generated inventories.
        start_sector: First included relative payload sector.
        end_sector: First excluded relative payload sector.
    """

    name: str
    start_sector: int
    end_sector: int

    def contains_sector(self, sector: int) -> bool:
        """Return whether a relative sector falls within this range.

        Args:
            sector: Relative 2048-byte Track 2 sector to test.

        Returns:
            ``True`` when ``sector`` is greater than or equal to
            ``start_sector`` and less than ``end_sector``.
        """

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
    """Map a relative Track 2 sector to an analysis-bank label.

    Args:
        sector: Sector index in the extracted 2048-byte payload.

    Returns:
        The matching ``BankRange.name``. ``BOOT`` is returned for negative
        sectors and sectors at or beyond the payload. The fallback name is
        historical because ``MISSION_0`` begins at sector zero.

    Notes:
        Returning a fallback instead of raising keeps forensic scanners able
        to label malformed or deliberately out-of-range candidates.
    """

    for bank in BANKS:
        if bank.contains_sector(sector):
            return bank.name
    return "BOOT"


def bank_for_offset(offset: int) -> str:
    """Map a payload byte offset to an analysis-bank label.

    Args:
        offset: Byte offset in the extracted 2048-byte-sector payload.

    Returns:
        The value returned by ``bank_for_sector(offset // SECTOR_SIZE)``.

    Notes:
        Negative offsets use Python floor division and therefore map to the
        ``BOOT`` fallback. Callers that require strict validation should
        reject negative offsets before calling this helper.
    """

    return bank_for_sector(offset // SECTOR_SIZE)


def payload_offset(sector: int, within_sector: int = 0) -> int:
    """Convert relative sector coordinates to a payload byte offset.

    Args:
        sector: Non-negative relative Track 2 sector.
        within_sector: Byte position within the 2048-byte user-data sector.

    Returns:
        ``sector * SECTOR_SIZE + within_sector``.

    Raises:
        ValueError: If ``sector`` is negative or ``within_sector`` lies
            outside ``0`` through ``SECTOR_SIZE - 1``.

    Notes:
        This helper does not require ``sector`` to be within the known Track
        2 sector count. That behavior permits calculations at an exclusive
        end boundary while still rejecting impossible in-sector positions.
    """

    if sector < 0:
        raise ValueError("sector must be non-negative")
    if not 0 <= within_sector < SECTOR_SIZE:
        raise ValueError(
            "within_sector must be in the range "
            f"0..{SECTOR_SIZE - 1}"
        )
    return sector * SECTOR_SIZE + within_sector


def absolute_lba(relative_sector: int) -> int:
    """Convert a relative Track 2 sector to an absolute CloneCD LBA.

    Args:
        relative_sector: Sector index relative to Track 2 INDEX 01.

    Returns:
        ``TRACK2_START_LBA + relative_sector``.

    Notes:
        The function intentionally performs arithmetic only. It accepts
        negative and out-of-range values so callers can calculate boundaries.
        Validate the result separately when addressing source-image data.
    """

    return TRACK2_START_LBA + relative_sector
