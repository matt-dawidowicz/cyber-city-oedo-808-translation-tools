"""Apply guarded payload patches with sector-indexed work scheduling."""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Iterable

from cyber_oedo.disc.cdrom_mode1 import (
    ModifiedSector,
    PayloadPatch,
    mode1_integrity_matches,
    rebuild_mode1_sector,
    validate_mode1_structure,
)
from cyber_oedo.io import sha256_buffer
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
)


def _ordered_patches(
    patches: Iterable[PayloadPatch],
    sector_count: int,
) -> tuple[PayloadPatch, ...]:
    """Validate payload bounds and non-overlap, then sort by offset."""

    if sector_count <= 0:
        raise ValueError("sector_count must be positive")
    ordered = tuple(sorted(patches, key=lambda patch: patch.offset))
    if not ordered:
        raise ValueError("at least one payload patch is required")
    payload_size = sector_count * SECTOR_SIZE
    previous_end = 0
    for index, patch in enumerate(ordered):
        if patch.end_offset > payload_size:
            raise ValueError(f"{patch.label}: patch ends beyond the payload")
        if index and patch.offset < previous_end:
            raise ValueError(f"{patch.label}: patch overlaps the previous replacement")
        previous_end = patch.end_offset
    return ordered


def _index_by_sector(
    patches: tuple[PayloadPatch, ...],
) -> dict[int, tuple[PayloadPatch, ...]]:
    """Index patches once so each sector sees only intersecting patches."""

    indexed: defaultdict[int, list[PayloadPatch]] = defaultdict(list)
    for patch in patches:
        first = patch.offset // SECTOR_SIZE
        last = (patch.end_offset - 1) // SECTOR_SIZE
        for relative_sector in range(first, last + 1):
            indexed[relative_sector].append(patch)
    return {sector: tuple(items) for sector, items in indexed.items()}


def _patch_sector(
    raw: bytes,
    relative_sector: int,
    patches: tuple[PayloadPatch, ...],
) -> tuple[bytes, int]:
    """Patch one raw sector using only its pre-indexed replacements."""

    sector_start = relative_sector * SECTOR_SIZE
    sector_end = sector_start + SECTOR_SIZE
    edited = bytearray(raw)
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
        if bytes(edited[raw_start:raw_end]) != expected:
            raise ValueError(
                f"{patch.label}: source bytes differ at payload 0x{overlap_start:08X}"
            )
        edited[raw_start:raw_end] = patch.replacement[patch_start:patch_end]
        edited_bytes += overlap_end - overlap_start
    return rebuild_mode1_sector(edited), edited_bytes


def _apply_payload_patches_in_place(
    image_path: pathlib.Path,
    patches: Iterable[PayloadPatch],
    *,
    start_lba: int,
    sector_count: int,
) -> tuple[ModifiedSector, ...]:
    """Validate all affected sectors before writing rebuilt sectors.

    Compared with the historical implementation, patch-to-sector membership is
    calculated once.  A sector therefore no longer scans the complete patch
    list, and a freshly rebuilt sector is not rebuilt a second time merely to
    prove that the deterministic rebuild function produced its own output.
    """

    if start_lba < 0:
        raise ValueError("start_lba must be non-negative")
    ordered = _ordered_patches(patches, sector_count)
    indexed = _index_by_sector(ordered)
    required_size = (start_lba + sector_count) * RAW_SECTOR_SIZE
    image_size = image_path.stat().st_size
    if image_size < required_size:
        raise ValueError(
            f"IMG is too short: need at least {required_size:,} bytes, "
            f"found {image_size:,}"
        )

    rebuilt_sectors: dict[int, bytes] = {}
    reports: list[ModifiedSector] = []
    with image_path.open("r+b") as image:
        for relative_sector in sorted(indexed):
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            raw = image.read(RAW_SECTOR_SIZE)
            if len(raw) != RAW_SECTOR_SIZE:
                raise ValueError(f"short read at absolute LBA {absolute_lba}")
            validate_mode1_structure(raw)
            if not mode1_integrity_matches(raw):
                raise ValueError(
                    f"original EDC/ECC mismatch at absolute LBA {absolute_lba}"
                )
            rebuilt, edited_bytes = _patch_sector(
                raw,
                relative_sector,
                indexed[relative_sector],
            )
            rebuilt_sectors[relative_sector] = rebuilt
            reports.append(
                ModifiedSector(
                    relative_sector=relative_sector,
                    absolute_lba=absolute_lba,
                    edited_payload_bytes=edited_bytes,
                    before_sha256=sha256_buffer(raw),
                    after_sha256=sha256_buffer(rebuilt),
                )
            )

        for relative_sector, rebuilt in rebuilt_sectors.items():
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            image.write(rebuilt)
        image.flush()

    return tuple(reports)


def apply_payload_patches(
    image_path: pathlib.Path,
    patches: Iterable[PayloadPatch],
    *,
    start_lba: int,
    sector_count: int,
    atomic: bool = True,
) -> tuple[ModifiedSector, ...]:
    """Patch a private copy and publish it atomically by default.

    Set atomic=False only for an already disposable, isolated working image,
    such as the staging directory managed by build_human_test_disc.
    """
    if not atomic:
        return _apply_payload_patches_in_place(
            image_path, patches, start_lba=start_lba, sector_count=sector_count
        )

    image_path = pathlib.Path(image_path)
    # Reject invalid arguments before incurring the cost of a full image copy.
    ordered = _ordered_patches(patches, sector_count)
    if start_lba < 0:
        raise ValueError("start_lba must be non-negative")
    required_size = (start_lba + sector_count) * RAW_SECTOR_SIZE
    if image_path.stat().st_size < required_size:
        raise ValueError("IMG is too short for the requested payload range")

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{image_path.name}.", suffix=".tmp", dir=image_path.parent
    )
    os.close(fd)
    temporary = pathlib.Path(temporary_name)
    try:
        shutil.copy2(image_path, temporary)
        reports = _apply_payload_patches_in_place(
            temporary, ordered, start_lba=start_lba, sector_count=sector_count
        )
        # Flush the temporary image to disk before publishing it.
        with temporary.open("rb") as staged:
            os.fsync(staged.fileno())
        os.replace(temporary, image_path)
        return reports
    finally:
        temporary.unlink(missing_ok=True)
