"""Serialize deterministic build evidence without owning patch behavior."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch

MANIFEST_INLINE_BINARY_LIMIT = 64


def text_patch_rows(
    text_patches: Iterable[object],
    *,
    sector_size: int,
    track_start_lba: int,
) -> list[dict[str, Any]]:
    """Serialize text-patch coordinates and exact translator evidence."""

    rows: list[dict[str, Any]] = []
    for patch in text_patches:
        payload_patch = patch.to_payload_patch()  # type: ignore[attr-defined]
        offset = patch.offset  # type: ignore[attr-defined]
        relative_sector = offset // sector_size
        rows.append(
            {
                "purpose": patch.purpose,  # type: ignore[attr-defined]
                "payload_offset": f"0x{offset:08X}",
                "relative_sector": relative_sector,
                "absolute_lba": track_start_lba + relative_sector,
                "source_text": patch.source_text,  # type: ignore[attr-defined]
                "english": patch.english,  # type: ignore[attr-defined]
                "wrap_width": patch.wrap_width,  # type: ignore[attr-defined]
                "formatted_english": (
                    patch.formatted_english  # type: ignore[attr-defined]
                ),
                "replacement_text": (
                    patch.replacement_text  # type: ignore[attr-defined]
                ),
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
            "expected_sha256": hashlib.sha256(patch.expected).hexdigest(),
            "replacement_sha256": hashlib.sha256(patch.replacement).hexdigest(),
            "bytes": len(patch.expected),
        }
        if len(patch.expected) <= inline_limit:
            row["expected_hex"] = patch.expected.hex(" ")
            row["replacement_hex"] = patch.replacement.hex(" ")
        rows.append(row)
    return rows
