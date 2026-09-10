"""Describe the human-test patch profile without exposing source bytes."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from cyber_oedo.io import sha256_buffer


@dataclass(frozen=True, slots=True)
class PatchPlanEntry:
    """Describe one planned replacement using hashes instead of raw bytes."""

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
    """Describe one complete stock-renderer build profile."""

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

        return sha256_buffer(self.canonical_json().encode("utf-8"))


def build_profile_plan(title_screen_mode: str) -> PatchPlan:
    """Build the deterministic hash-only plan from the canonical recipe."""

    from cyber_oedo.build.recipe import prepare_build_recipe

    return prepare_build_recipe(title_screen_mode).patch_plan()


__all__ = ["PatchPlan", "PatchPlanEntry", "build_profile_plan"]
