#!/usr/bin/env python3
"""Rebuild and patch raw CD-ROM Mode 1 sectors safely.

CloneCD stores this game's data track as 2352-byte raw sectors. Modifying the
2048-byte user-data area invalidates the sector's error-detection code (EDC)
and P/Q error-correction code (ECC). This module implements the standard
CD-ROM Mode 1 calculations and applies payload-coordinate patches only after
validating source bytes, sector structure, integrity fields, bounds, and
overlap.

The patching functions operate on a disposable image copy. They do not copy a
disc image, alter CloneCD metadata, or make any claim that a text replacement
fits the game's renderer. Higher-level build tools remain responsible for
source identity, output isolation, encoding rules, and whole-image comparison.
"""

from __future__ import annotations

import hashlib
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass

from game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
)


MODE1_SYNC = b"\x00" + (b"\xFF" * 10) + b"\x00"
MODE1_EDC_OFFSET = 2064
MODE1_RESERVED_OFFSET = 2068
MODE1_ECC_P_OFFSET = 2076
MODE1_ECC_Q_OFFSET = 2248


@dataclass(frozen=True, slots=True)
class PayloadPatch:
    """Describe one same-size replacement in payload coordinates.

    Attributes:
        offset: Byte offset in the flat 2048-byte-sector Track 2 payload.
        expected: Exact bytes that must exist before patching.
        replacement: Bytes to write. Length must equal ``expected``.
        label: Human-readable purpose included in errors and reports.

    Notes:
        Equal-length replacement is mandatory. This type does not represent
        relocation, pointer changes, insertion, or deletion.
    """

    offset: int
    expected: bytes
    replacement: bytes
    label: str

    def __post_init__(self) -> None:
        """Reject invalid coordinates, empty patches, and size changes.

        Raises:
            ValueError: If the offset is negative, the patch is empty, source
                and replacement lengths differ, or the label is blank.
        """

        if self.offset < 0:
            raise ValueError("patch offset must be non-negative")
        if not self.expected:
            raise ValueError("patch data must not be empty")
        if len(self.expected) != len(self.replacement):
            raise ValueError(
                "expected and replacement byte lengths must match"
            )
        if not self.label.strip():
            raise ValueError("patch label must not be blank")

    @property
    def end_offset(self) -> int:
        """Return the exclusive payload end offset.

        Returns:
            ``offset + len(expected)``.
        """

        return self.offset + len(self.expected)


@dataclass(frozen=True, slots=True)
class ModifiedSector:
    """Record the identity of one rebuilt raw sector.

    Attributes:
        relative_sector: Sector index relative to Track 2 INDEX 01.
        absolute_lba: Raw CloneCD sector index in the complete IMG.
        edited_payload_bytes: Number of user-data bytes targeted in the sector.
        before_sha256: SHA-256 of the original 2352-byte raw sector.
        after_sha256: SHA-256 of the rebuilt 2352-byte raw sector.
    """

    relative_sector: int
    absolute_lba: int
    edited_payload_bytes: int
    before_sha256: str
    after_sha256: str


def _build_ecc_tables() -> tuple[bytes, bytes]:
    """Build the forward and reverse Galois-field lookup tables.

    Returns:
        A tuple containing 256-byte forward and reverse tables for the
        CD-ROM ECC polynomial.

    Notes:
        Tables are generated once at import time to keep the implementation
        auditable without embedding unexplained binary constants.
    """

    forward = bytearray(256)
    reverse = bytearray(256)
    for value in range(256):
        doubled = value << 1
        if doubled & 0x100:
            doubled ^= 0x11D
        forward[value] = doubled
        reverse[value ^ doubled] = value
    return bytes(forward), bytes(reverse)


def _build_edc_table() -> tuple[int, ...]:
    """Build the CD-ROM EDC lookup table.

    Returns:
        A 256-entry tuple generated with reflected polynomial
        ``0xD8018001``.
    """

    table: list[int] = []
    for value in range(256):
        remainder = value
        for _ in range(8):
            if remainder & 1:
                remainder = (remainder >> 1) ^ 0xD8018001
            else:
                remainder >>= 1
        table.append(remainder)
    return tuple(table)


ECC_FORWARD, ECC_REVERSE = _build_ecc_tables()
EDC_TABLE = _build_edc_table()


def compute_edc(
    data: bytes | bytearray | memoryview,
    *,
    initial: int = 0,
) -> int:
    """Compute the standard CD-ROM error-detection code.

    Args:
        data: Bytes covered by the EDC calculation.
        initial: Unsigned 32-bit initial accumulator, normally zero.

    Returns:
        Unsigned 32-bit EDC value. Raw Mode 1 sectors store this integer in
        little-endian order.

    Raises:
        ValueError: If ``initial`` is outside the unsigned 32-bit range.
    """

    if not 0 <= initial <= 0xFFFFFFFF:
        raise ValueError("initial EDC must be an unsigned 32-bit integer")
    value = initial
    for byte in data:
        value = (value >> 8) ^ EDC_TABLE[(value ^ byte) & 0xFF]
    return value


def _compute_ecc(
    source: bytes | bytearray | memoryview,
    *,
    major_count: int,
    minor_count: int,
    major_multiplier: int,
    minor_increment: int,
) -> bytes:
    """Compute one interleaved CD-ROM ECC parity block.

    Args:
        source: Exact source block used by the P or Q pass.
        major_count: Number of major parity rows.
        minor_count: Source symbols consumed per major row.
        major_multiplier: Starting-index multiplier for each major row.
        minor_increment: Wrapped source stride between symbols.

    Returns:
        ``major_count * 2`` parity bytes.

    Raises:
        ValueError: If parameters are not positive or source length differs
            from ``major_count * minor_count``.
    """

    parameters = (
        major_count,
        minor_count,
        major_multiplier,
        minor_increment,
    )
    if any(value <= 0 for value in parameters):
        raise ValueError("ECC parameters must be positive")
    size = major_count * minor_count
    if len(source) != size:
        raise ValueError(
            f"ECC source must contain {size} bytes, found {len(source)}"
        )

    destination = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_multiplier + (major & 1)
        parity_a = 0
        parity_b = 0
        for _ in range(minor_count):
            symbol = source[index]
            index += minor_increment
            if index >= size:
                index -= size
            parity_a ^= symbol
            parity_b ^= symbol
            parity_a = ECC_FORWARD[parity_a]
        parity_a = ECC_REVERSE[ECC_FORWARD[parity_a] ^ parity_b]
        destination[major] = parity_a
        destination[major + major_count] = parity_a ^ parity_b
    return bytes(destination)


def validate_mode1_structure(raw_sector: bytes | bytearray) -> None:
    """Validate raw-sector size, synchronization pattern, and mode byte.

    Args:
        raw_sector: One complete 2352-byte raw sector.

    Raises:
        ValueError: If the sector has the wrong size, invalid sync bytes, or a
            mode byte other than ``01``.
    """

    if len(raw_sector) != RAW_SECTOR_SIZE:
        raise ValueError(
            f"raw sector must contain {RAW_SECTOR_SIZE} bytes, "
            f"found {len(raw_sector)}"
        )
    if raw_sector[: len(MODE1_SYNC)] != MODE1_SYNC:
        raise ValueError("raw sector has an invalid synchronization pattern")
    if raw_sector[15] != 1:
        raise ValueError(
            f"raw sector is mode {raw_sector[15]:02X}, not Mode 1"
        )


def rebuild_mode1_sector(raw_sector: bytes | bytearray) -> bytes:
    """Return a Mode 1 sector with regenerated EDC and ECC fields.

    Args:
        raw_sector: One structurally valid 2352-byte Mode 1 sector containing
            the desired user data.

    Returns:
        A new immutable sector with little-endian EDC, eight reserved zero
        bytes, and regenerated P and Q parity.

    Raises:
        ValueError: If structural validation fails.

    Design Decisions:
        The sync, address, mode, and user-data bytes are preserved. Mode 1
        requires the reserved field to be zero before ECC generation.
    """

    validate_mode1_structure(raw_sector)
    rebuilt = bytearray(raw_sector)
    edc = compute_edc(rebuilt[:MODE1_EDC_OFFSET])
    rebuilt[
        MODE1_EDC_OFFSET:MODE1_RESERVED_OFFSET
    ] = edc.to_bytes(4, "little")
    rebuilt[MODE1_RESERVED_OFFSET:MODE1_ECC_P_OFFSET] = bytes(8)
    rebuilt[MODE1_ECC_P_OFFSET:MODE1_ECC_Q_OFFSET] = _compute_ecc(
        rebuilt[12:MODE1_ECC_P_OFFSET],
        major_count=86,
        minor_count=24,
        major_multiplier=2,
        minor_increment=86,
    )
    rebuilt[MODE1_ECC_Q_OFFSET:RAW_SECTOR_SIZE] = _compute_ecc(
        rebuilt[12:MODE1_ECC_Q_OFFSET],
        major_count=52,
        minor_count=43,
        major_multiplier=86,
        minor_increment=88,
    )
    return bytes(rebuilt)


def mode1_integrity_matches(raw_sector: bytes | bytearray) -> bool:
    """Return whether a raw Mode 1 sector's EDC and ECC are current.

    Args:
        raw_sector: One complete raw Mode 1 sector.

    Returns:
        ``True`` when rebuilding produces byte-identical data.

    Raises:
        ValueError: If structural validation fails.
    """

    return rebuild_mode1_sector(raw_sector) == bytes(raw_sector)


def read_payload_range(
    image_path: pathlib.Path,
    offset: int,
    size: int,
    *,
    start_lba: int,
    sector_count: int,
) -> bytes:
    """Read a validated byte range from raw Mode 1 payload sectors.

    Args:
        image_path: Raw CloneCD IMG containing the payload.
        offset: Byte offset relative to payload sector zero.
        size: Positive number of payload bytes to return.
        start_lba: Absolute IMG sector corresponding to payload sector zero.
        sector_count: Number of valid Mode 1 payload sectors.

    Returns:
        Exactly ``size`` bytes assembled across one or more user-data areas.

    Raises:
        OSError: If image metadata, seeks, or reads fail.
        ValueError: If arguments, bounds, image size, sector structure, or
            original EDC/ECC fields are invalid.

    Side Effects:
        Opens and reads ``image_path`` without modifying it.

    Design Decisions:
        Source bytes used as guards for large generated patches must come from
        the authenticated disc rather than being redistributed in this
        repository. Verifying every touched raw sector retains the same trust
        boundary used by ``apply_payload_patches``.
    """

    if offset < 0:
        raise ValueError("payload offset must be non-negative")
    if size <= 0:
        raise ValueError("payload read size must be positive")
    if start_lba < 0:
        raise ValueError("start_lba must be non-negative")
    if sector_count <= 0:
        raise ValueError("sector_count must be positive")
    payload_size = sector_count * SECTOR_SIZE
    if offset + size > payload_size:
        raise ValueError("payload range ends beyond the available sectors")

    required_size = (start_lba + sector_count) * RAW_SECTOR_SIZE
    image_size = image_path.stat().st_size
    if image_size < required_size:
        raise ValueError(
            f"IMG is too short: need at least {required_size:,} bytes, "
            f"found {image_size:,}"
        )

    first_sector = offset // SECTOR_SIZE
    last_sector = (offset + size - 1) // SECTOR_SIZE
    result = bytearray()
    with image_path.open("rb") as image:
        for relative_sector in range(first_sector, last_sector + 1):
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            raw = image.read(RAW_SECTOR_SIZE)
            if len(raw) != RAW_SECTOR_SIZE:
                raise ValueError(
                    f"short read at absolute LBA {absolute_lba}"
                )
            validate_mode1_structure(raw)
            if not mode1_integrity_matches(raw):
                raise ValueError(
                    f"original EDC/ECC mismatch at absolute LBA "
                    f"{absolute_lba}"
                )

            sector_payload_start = relative_sector * SECTOR_SIZE
            overlap_start = max(offset, sector_payload_start)
            overlap_end = min(
                offset + size,
                sector_payload_start + SECTOR_SIZE,
            )
            raw_start = (
                MODE1_USER_DATA_OFFSET
                + overlap_start
                - sector_payload_start
            )
            raw_end = (
                MODE1_USER_DATA_OFFSET
                + overlap_end
                - sector_payload_start
            )
            result.extend(raw[raw_start:raw_end])

    if len(result) != size:
        raise AssertionError("payload range reader returned the wrong size")
    return bytes(result)


def _validate_patch_set(
    patches: Iterable[PayloadPatch],
    *,
    sector_count: int,
) -> tuple[PayloadPatch, ...]:
    """Validate ordering, bounds, and non-overlap for payload patches.

    Args:
        patches: Candidate same-size payload replacements.
        sector_count: Number of available 2048-byte payload sectors.

    Returns:
        Patches sorted by payload offset.

    Raises:
        ValueError: If the sector count is not positive, no patches are
            supplied, a patch exceeds the payload, or patches overlap.
    """

    if sector_count <= 0:
        raise ValueError("sector_count must be positive")
    ordered = tuple(sorted(patches, key=lambda patch: patch.offset))
    if not ordered:
        raise ValueError("at least one payload patch is required")

    payload_size = sector_count * SECTOR_SIZE
    previous_end = 0
    for index, patch in enumerate(ordered):
        if patch.end_offset > payload_size:
            raise ValueError(
                f"{patch.label}: patch ends beyond the payload"
            )
        if index and patch.offset < previous_end:
            raise ValueError(
                f"{patch.label}: patch overlaps the previous replacement"
            )
        previous_end = patch.end_offset
    return ordered


def _patch_sector_data(
    sector_data: bytearray,
    *,
    relative_sector: int,
    patches: tuple[PayloadPatch, ...],
) -> int:
    """Apply all intersecting patches to one sector's user-data area.

    Args:
        sector_data: Mutable 2352-byte raw sector.
        relative_sector: Track-relative payload sector represented by the data.
        patches: Globally validated and sorted payload patches.

    Returns:
        Number of user-data bytes targeted in this sector.

    Raises:
        ValueError: If any source bytes differ from a patch's expectation.
    """

    sector_start = relative_sector * SECTOR_SIZE
    sector_end = sector_start + SECTOR_SIZE
    edited_bytes = 0
    for patch in patches:
        overlap_start = max(patch.offset, sector_start)
        overlap_end = min(patch.end_offset, sector_end)
        if overlap_start >= overlap_end:
            continue

        patch_start = overlap_start - patch.offset
        patch_end = overlap_end - patch.offset
        user_start = overlap_start - sector_start
        user_end = overlap_end - sector_start
        raw_start = MODE1_USER_DATA_OFFSET + user_start
        raw_end = MODE1_USER_DATA_OFFSET + user_end
        expected = patch.expected[patch_start:patch_end]
        actual = bytes(sector_data[raw_start:raw_end])
        if actual != expected:
            raise ValueError(
                f"{patch.label}: source bytes differ at payload "
                f"0x{overlap_start:08X}"
            )
        sector_data[raw_start:raw_end] = patch.replacement[
            patch_start:patch_end
        ]
        edited_bytes += overlap_end - overlap_start
    return edited_bytes


def apply_payload_patches(
    image_path: pathlib.Path,
    patches: Iterable[PayloadPatch],
    *,
    start_lba: int,
    sector_count: int,
) -> tuple[ModifiedSector, ...]:
    """Apply payload patches and rebuild every affected raw sector.

    All source checks and sector rebuilds complete in memory before the first
    write. A validation failure therefore leaves the image unchanged.

    Args:
        image_path: Disposable raw CloneCD IMG to modify in place.
        patches: Same-size replacements expressed in payload coordinates.
        start_lba: Absolute IMG sector corresponding to payload sector zero.
        sector_count: Number of valid Mode 1 payload sectors.

    Returns:
        One ``ModifiedSector`` per affected relative sector, sorted by sector.

    Raises:
        OSError: If image metadata, reads, seeks, or writes fail.
        ValueError: If arguments, image size, source bytes, structure, original
            integrity fields, bounds, or patch overlap are invalid.

    Side Effects:
        Replaces complete 2352-byte sectors in ``image_path`` only after all
        affected sectors have passed validation and been rebuilt.
    """

    if start_lba < 0:
        raise ValueError("start_lba must be non-negative")
    ordered = _validate_patch_set(patches, sector_count=sector_count)
    required_size = (start_lba + sector_count) * RAW_SECTOR_SIZE
    image_size = image_path.stat().st_size
    if image_size < required_size:
        raise ValueError(
            f"IMG is too short: need at least {required_size:,} bytes, "
            f"found {image_size:,}"
        )

    affected = sorted(
        {
            relative_sector
            for patch in ordered
            for relative_sector in range(
                patch.offset // SECTOR_SIZE,
                ((patch.end_offset - 1) // SECTOR_SIZE) + 1,
            )
        }
    )
    rebuilt_sectors: dict[int, bytes] = {}
    reports: list[ModifiedSector] = []
    with image_path.open("r+b") as image:
        for relative_sector in affected:
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            raw = image.read(RAW_SECTOR_SIZE)
            if len(raw) != RAW_SECTOR_SIZE:
                raise ValueError(
                    f"short read at absolute LBA {absolute_lba}"
                )
            validate_mode1_structure(raw)
            if not mode1_integrity_matches(raw):
                raise ValueError(
                    f"original EDC/ECC mismatch at absolute LBA "
                    f"{absolute_lba}"
                )

            edited = bytearray(raw)
            edited_bytes = _patch_sector_data(
                edited,
                relative_sector=relative_sector,
                patches=ordered,
            )
            rebuilt = rebuild_mode1_sector(edited)
            if not mode1_integrity_matches(rebuilt):
                raise AssertionError(
                    f"internal EDC/ECC rebuild failure at LBA {absolute_lba}"
                )
            rebuilt_sectors[relative_sector] = rebuilt
            reports.append(
                ModifiedSector(
                    relative_sector=relative_sector,
                    absolute_lba=absolute_lba,
                    edited_payload_bytes=edited_bytes,
                    before_sha256=hashlib.sha256(raw).hexdigest(),
                    after_sha256=hashlib.sha256(rebuilt).hexdigest(),
                )
            )

        for relative_sector in affected:
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            image.write(rebuilt_sectors[relative_sector])
        image.flush()

    return tuple(reports)
