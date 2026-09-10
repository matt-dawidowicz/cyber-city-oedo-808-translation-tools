"""Efficient independent verification for patched raw CloneCD images."""

from __future__ import annotations

import hashlib
import pathlib
from collections import defaultdict
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import (
    PayloadPatch,
    mode1_integrity_matches,
    validate_mode1_structure,
)
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
)

DEFAULT_COMPARE_SECTORS = 2048


@dataclass(frozen=True, slots=True)
class ImageComparison:
    """Result of one combined whole-image compare and output hash pass."""

    changed_lbas: tuple[int, ...]
    output_sha256: str


def compare_and_hash_raw_images(
    source_image: pathlib.Path,
    output_image: pathlib.Path,
    *,
    chunk_sectors: int = DEFAULT_COMPARE_SECTORS,
) -> ImageComparison:
    """Compare raw images in large aligned chunks while hashing output.

    Identical multi-megabyte chunks are skipped without per-sector Python
    comparisons.  Only chunks that differ are split into raw sectors to locate
    exact changed LBAs.  This replaces hundreds of thousands of tiny reads and
    removes the later full-file output hashing pass.
    """

    if chunk_sectors <= 0:
        raise ValueError("chunk_sectors must be positive")
    source_size = source_image.stat().st_size
    output_size = output_image.stat().st_size
    if source_size != output_size:
        raise ValueError(f"IMG size changed: {source_size:,} != {output_size:,}")
    if source_size % RAW_SECTOR_SIZE:
        raise ValueError("IMG size is not divisible by 2352")

    chunk_bytes = chunk_sectors * RAW_SECTOR_SIZE
    changed: list[int] = []
    output_digest = hashlib.sha256()
    first_lba = 0
    with source_image.open("rb") as source, output_image.open("rb") as output:
        while True:
            source_chunk = source.read(chunk_bytes)
            output_chunk = output.read(chunk_bytes)
            if not source_chunk and not output_chunk:
                break
            if len(source_chunk) != len(output_chunk):
                raise ValueError("short or asymmetric raw image read")
            output_digest.update(output_chunk)
            if source_chunk != output_chunk:
                sector_count = len(source_chunk) // RAW_SECTOR_SIZE
                for index in range(sector_count):
                    start = index * RAW_SECTOR_SIZE
                    end = start + RAW_SECTOR_SIZE
                    if source_chunk[start:end] != output_chunk[start:end]:
                        changed.append(first_lba + index)
            first_lba += len(source_chunk) // RAW_SECTOR_SIZE

    return ImageComparison(
        changed_lbas=tuple(changed),
        output_sha256=output_digest.hexdigest(),
    )


def _replacement_slices(
    patches: tuple[PayloadPatch, ...],
) -> dict[int, tuple[tuple[int, bytes, str], ...]]:
    """Split patch replacements into sector-local verification slices."""

    indexed: defaultdict[int, list[tuple[int, bytes, str]]] = defaultdict(list)
    for patch in patches:
        checked = 0
        while checked < len(patch.replacement):
            payload_position = patch.offset + checked
            relative_sector = payload_position // SECTOR_SIZE
            within_sector = payload_position % SECTOR_SIZE
            size = min(
                len(patch.replacement) - checked,
                SECTOR_SIZE - within_sector,
            )
            replacement = patch.replacement[checked : checked + size]
            indexed[relative_sector].append((within_sector, replacement, patch.label))
            checked += size
    return {sector: tuple(items) for sector, items in indexed.items()}


def verify_output_patches(
    output_image: pathlib.Path,
    patches: tuple[PayloadPatch, ...],
    *,
    start_lba: int,
) -> None:
    """Read every affected output sector once and verify all replacements."""

    indexed = _replacement_slices(patches)
    with output_image.open("rb") as image:
        for relative_sector in sorted(indexed):
            absolute_lba = start_lba + relative_sector
            image.seek(absolute_lba * RAW_SECTOR_SIZE)
            raw = image.read(RAW_SECTOR_SIZE)
            if len(raw) != RAW_SECTOR_SIZE:
                raise ValueError(f"short read at absolute LBA {absolute_lba}")
            validate_mode1_structure(raw)
            if not mode1_integrity_matches(raw):
                raise ValueError(
                    f"rebuilt EDC/ECC mismatch at absolute LBA {absolute_lba}"
                )
            for within_sector, replacement, label in indexed[relative_sector]:
                start = MODE1_USER_DATA_OFFSET + within_sector
                end = start + len(replacement)
                if raw[start:end] != replacement:
                    raise ValueError(f"{label}: output verification failed")
