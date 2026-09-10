"""Prepare one typed build recipe for planning, manifests, and execution."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from cyber_oedo.build.plan import PatchPlan, PatchPlanEntry
from cyber_oedo.build.profiles import mission0_stock as profile
from cyber_oedo.build.profiles.models import InPlaceTextPatch
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.io import sha256_buffer


@dataclass(frozen=True, slots=True)
class PreparedPatch:
    """Pair one hash-only plan entry with its optional materialized mutation."""

    category: str
    plan_entry: PatchPlanEntry
    payload_patch: PayloadPatch | None
    text_patch: InPlaceTextPatch | None = None


@dataclass(frozen=True, slots=True)
class BuildRecipe:
    """Canonical prepared build description shared by all build consumers.

    A source-independent recipe is sufficient for hash-only planning.  Clean
    title-screen recipes become fully materialized only when an authenticated
    source IMG is supplied, because those source bytes are intentionally not
    stored in the repository.
    """

    build_profile: str
    title_screen_mode: str
    patches: tuple[PreparedPatch, ...]
    guarded_relative_sectors: tuple[int, ...]

    @property
    def text_patches(self) -> tuple[PreparedPatch, ...]:
        """Return prepared text mutations in stable profile order."""

        return tuple(item for item in self.patches if item.text_patch is not None)

    @property
    def binary_patches(self) -> tuple[PreparedPatch, ...]:
        """Return prepared layout/title mutations in stable profile order."""

        return tuple(item for item in self.patches if item.text_patch is None)

    def payload_patches(self) -> tuple[PayloadPatch, ...]:
        """Return every materialized mutation or reject a hash-only recipe."""

        missing = [item.plan_entry.label for item in self.patches if item.payload_patch is None]
        if missing:
            raise ValueError(
                "build recipe is hash-only; authenticated source bytes are required for: "
                + ", ".join(missing)
            )
        return tuple(item.payload_patch for item in self.patches if item.payload_patch is not None)

    def patch_plan(self) -> PatchPlan:
        """Project this recipe to the deterministic hash-only review contract."""

        return PatchPlan(
            build_profile=self.build_profile,
            title_screen_mode=self.title_screen_mode,
            entries=tuple(item.plan_entry for item in self.patches),
            guarded_relative_sectors=self.guarded_relative_sectors,
        )


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Return build outputs and reviewed counts without rereading the manifest."""

    output_ccd: pathlib.Path
    manifest_path: pathlib.Path
    build_profile: str
    title_screen_mode: str
    text_patch_count: int
    binary_patch_count: int
    changed_relative_sectors: tuple[int, ...]
    guarded_relative_sectors: tuple[int, ...]
    plan_sha256: str


def _entry(category: str, patch: PayloadPatch) -> PatchPlanEntry:
    return PatchPlanEntry(
        category=category,
        label=patch.label,
        offset=patch.offset,
        byte_count=len(patch.expected),
        expected_sha256=sha256_buffer(patch.expected),
        replacement_sha256=sha256_buffer(patch.replacement),
    )


def _title_recipe(source_image: pathlib.Path | None) -> tuple[PreparedPatch, ...]:
    palette = profile.build_grayscale_title_palette_cycle()
    title = profile.build_clean_title_asset()
    descriptors = (
        PatchPlanEntry(
            category="title",
            label="optional antialiased opening title palette",
            offset=profile.TITLE_PALETTE_OFFSET,
            byte_count=profile.TITLE_PALETTE_BYTES,
            expected_sha256=profile.TITLE_PALETTE_SOURCE_SHA256,
            replacement_sha256=sha256_buffer(palette),
        ),
        PatchPlanEntry(
            category="title",
            label="optional antialiased opening title graphic",
            offset=profile.TITLE_SCREEN_OFFSET,
            byte_count=profile.TITLE_ASSET_BYTES,
            expected_sha256=profile.TITLE_SCREEN_SOURCE_SHA256,
            replacement_sha256=sha256_buffer(title),
        ),
    )
    if source_image is None:
        return tuple(PreparedPatch("title", item, None) for item in descriptors)

    materialized = profile.optional_title_screen_patches(source_image, "clean")
    if len(materialized) != len(descriptors):
        raise AssertionError("clean title recipe changed patch count")
    prepared: list[PreparedPatch] = []
    for descriptor, patch in zip(descriptors, materialized, strict=True):
        actual = _entry("title", patch)
        if actual != descriptor:
            raise ValueError("materialized title patch differs from hash-only recipe")
        prepared.append(PreparedPatch("title", descriptor, patch))
    return tuple(prepared)


def _sectors(patches: tuple[PreparedPatch, ...]) -> tuple[int, ...]:
    sectors: set[int] = set()
    for item in patches:
        entry = item.plan_entry
        first = entry.offset // profile.SECTOR_SIZE
        last = (entry.end_offset - 1) // profile.SECTOR_SIZE
        sectors.update(range(first, last + 1))
    return tuple(sorted(sectors))


def prepare_build_recipe(
    title_screen_mode: str,
    *,
    source_image: pathlib.Path | None = None,
) -> BuildRecipe:
    """Prepare the single canonical patch set for planning or execution."""

    if title_screen_mode not in profile.TITLE_SCREEN_MODES:
        raise ValueError(f"title screen must be one of {profile.TITLE_SCREEN_MODES}")

    prepared: list[PreparedPatch] = []
    for text_patch in profile.HUMAN_TEST_PATCHES:
        payload_patch = text_patch.to_payload_patch()
        prepared.append(
            PreparedPatch(
                category="text",
                plan_entry=_entry("text", payload_patch),
                payload_patch=payload_patch,
                text_patch=text_patch,
            )
        )
    for payload_patch in profile.HUMAN_TEST_BINARY_PATCHES:
        prepared.append(
            PreparedPatch(
                category="layout",
                plan_entry=_entry("layout", payload_patch),
                payload_patch=payload_patch,
            )
        )
    if title_screen_mode == "clean":
        prepared.extend(_title_recipe(source_image))

    patches = tuple(prepared)
    sectors = _sectors(patches)
    expected = profile.profile_relative_sectors(title_screen_mode)
    if sectors != expected:
        raise ValueError("prepared recipe disagrees with independent profile footprint")
    return BuildRecipe(
        build_profile=profile.BUILD_PROFILE,
        title_screen_mode=title_screen_mode,
        patches=patches,
        guarded_relative_sectors=sectors,
    )


__all__ = ["BuildRecipe", "BuildResult", "PreparedPatch", "prepare_build_recipe"]
