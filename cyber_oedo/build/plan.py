"""Describe the human-test patch profile without exposing source bytes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from cyber_oedo.build.profiles import mission0_stock as profile


@dataclass(frozen=True, slots=True)
class PatchPlanEntry:
    """Describe one planned replacement using hashes instead of raw bytes.

    Args:
        category: Stable patch category used for review and reporting.
        label: Human-readable patch label from the guarded implementation.
        offset: Track 2 payload byte offset.
        byte_count: Number of same-size guarded bytes.
        expected_sha256: SHA-256 identity of the required source bytes.
        replacement_sha256: SHA-256 identity of the replacement bytes.
    """

    category: str
    label: str
    offset: int
    byte_count: int
    expected_sha256: str
    replacement_sha256: str

    @property
    def end_offset(self) -> int:
        """Return the exclusive payload end offset for this entry."""

        return self.offset + self.byte_count


@dataclass(frozen=True, slots=True)
class PatchPlan:
    """Describe one complete stock-renderer build profile.

    Args:
        build_profile: Stable profile identifier from the build profile.
        title_screen_mode: Selected title-screen variant.
        entries: Ordered hash-only patch descriptions.
        guarded_relative_sectors: Complete payload-sector footprint.
    """

    build_profile: str
    title_screen_mode: str
    entries: tuple[PatchPlanEntry, ...]
    guarded_relative_sectors: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe deterministic representation of the plan."""

        return {
            "build_profile": self.build_profile,
            "title_screen_mode": self.title_screen_mode,
            "entries": [asdict(entry) for entry in self.entries],
            "guarded_relative_sectors": list(self.guarded_relative_sectors),
        }

    def canonical_json(self) -> str:
        """Return stable compact JSON suitable for hashing and comparison."""

        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def sha256(self) -> str:
        """Return the SHA-256 identity of the canonical plan JSON."""

        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _entry_from_payload_patch(
    category: str,
    patch: object,
) -> PatchPlanEntry:
    """Convert one guarded payload patch into a hash-only plan entry."""

    expected = patch.expected
    replacement = patch.replacement
    return PatchPlanEntry(
        category=category,
        label=patch.label,
        offset=patch.offset,
        byte_count=len(expected),
        expected_sha256=hashlib.sha256(expected).hexdigest(),
        replacement_sha256=hashlib.sha256(replacement).hexdigest(),
    )


def _title_entries() -> tuple[PatchPlanEntry, PatchPlanEntry]:
    """Return source-independent identities for the optional title patches."""

    palette = profile.build_grayscale_title_palette_cycle()
    title = profile.build_clean_title_asset()
    return (
        PatchPlanEntry(
            category="title",
            label="optional antialiased opening title palette",
            offset=profile.TITLE_PALETTE_OFFSET,
            byte_count=profile.TITLE_PALETTE_BYTES,
            expected_sha256=profile.TITLE_PALETTE_SOURCE_SHA256,
            replacement_sha256=hashlib.sha256(palette).hexdigest(),
        ),
        PatchPlanEntry(
            category="title",
            label="optional antialiased opening title graphic",
            offset=profile.TITLE_SCREEN_OFFSET,
            byte_count=profile.TITLE_ASSET_BYTES,
            expected_sha256=profile.TITLE_SCREEN_SOURCE_SHA256,
            replacement_sha256=hashlib.sha256(title).hexdigest(),
        ),
    )


def _sectors_for_entries(
    entries: tuple[PatchPlanEntry, ...],
) -> tuple[int, ...]:
    """Return the complete relative-sector footprint for plan entries."""

    sectors: set[int] = set()
    for entry in entries:
        first = entry.offset // profile.SECTOR_SIZE
        last = (entry.end_offset - 1) // profile.SECTOR_SIZE
        sectors.update(range(first, last + 1))
    return tuple(sorted(sectors))


def build_profile_plan(title_screen_mode: str) -> PatchPlan:
    """Build the deterministic hash-only plan for one title variant.

    Args:
        title_screen_mode: ``"clean"`` or ``"original"``.

    Returns:
        Complete ordered patch plan without embedding copyrighted source bytes.

    Raises:
        ValueError: If the title mode is invalid or the derived sector
            footprint disagrees with the build engine's independent helper.
    """

    expected_sectors = profile.profile_relative_sectors(title_screen_mode)
    text_patches = tuple(item.to_payload_patch() for item in profile.HUMAN_TEST_PATCHES)
    entries = tuple(
        _entry_from_payload_patch("text", patch) for patch in text_patches
    ) + tuple(
        _entry_from_payload_patch("layout", patch)
        for patch in profile.HUMAN_TEST_BINARY_PATCHES
    )
    if title_screen_mode == "clean":
        entries += _title_entries()
    sectors = _sectors_for_entries(entries)
    if sectors != expected_sectors:
        raise ValueError("derived patch plan disagrees with profile sector footprint")
    return PatchPlan(
        build_profile=profile.BUILD_PROFILE,
        title_screen_mode=title_screen_mode,
        entries=entries,
        guarded_relative_sectors=sectors,
    )
