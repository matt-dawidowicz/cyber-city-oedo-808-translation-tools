"""Serialize deterministic build evidence without owning patch behavior."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, TYPE_CHECKING

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.io import sha256_buffer

if TYPE_CHECKING:
    from cyber_oedo.build.recipe import PreparedPatch

MANIFEST_INLINE_BINARY_LIMIT = 64


def text_patch_rows(
    prepared_patches: Iterable["PreparedPatch"],
    *,
    sector_size: int,
    track_start_lba: int,
) -> list[dict[str, Any]]:
    """Serialize text rows from the already-materialized build recipe."""

    rows: list[dict[str, Any]] = []
    for prepared in prepared_patches:
        patch = prepared.text_patch
        payload_patch = prepared.payload_patch
        if patch is None or payload_patch is None:
            raise ValueError("manifest text rows require materialized text patches")
        offset = patch.offset
        relative_sector = offset // sector_size
        rows.append(
            {
                "purpose": patch.purpose,
                "payload_offset": f"0x{offset:08X}",
                "relative_sector": relative_sector,
                "absolute_lba": track_start_lba + relative_sector,
                "source_text": patch.source_text,
                "english": patch.english,
                "wrap_width": patch.wrap_width,
                "formatted_english": patch.formatted_english,
                "replacement_text": patch.replacement_text,
                "bytes": len(payload_patch.expected),
            }
        )
    return rows


def binary_patch_rows(
    binary_patches: Iterable[PayloadPatch],
    *,
    sector_size: int,
    track_start_lba: int,
    inline_limit: int = MANIFEST_INLINE_BINARY_LIMIT,
) -> list[dict[str, Any]]:
    """Serialize binary-patch hashes and small exact before/after bytes."""

    if inline_limit < 0:
        raise ValueError("inline_limit must not be negative")
    rows: list[dict[str, Any]] = []
    for patch in binary_patches:
        relative_sector = patch.offset // sector_size
        row: dict[str, Any] = {
            "purpose": patch.label,
            "payload_offset": f"0x{patch.offset:08X}",
            "relative_sector": relative_sector,
            "absolute_lba": track_start_lba + relative_sector,
            "expected_sha256": sha256_buffer(patch.expected),
            "replacement_sha256": sha256_buffer(patch.replacement),
            "bytes": len(patch.expected),
        }
        if len(patch.expected) <= inline_limit:
            row["expected_hex"] = patch.expected.hex(" ")
            row["replacement_hex"] = patch.replacement.hex(" ")
        rows.append(row)
    return rows
