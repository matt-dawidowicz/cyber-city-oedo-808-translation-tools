"""Orchestrate the authenticated human-test build with one prepared recipe."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import shutil
import tempfile

from cyber_oedo.build.image_verify import compare_and_hash_raw_images, verify_output_patches
from cyber_oedo.build.manifest import binary_patch_rows, text_patch_rows
from cyber_oedo.build.profiles import mission0_stock as profile
from cyber_oedo.build.recipe import BuildResult, prepare_build_recipe
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.build.verification import verify_plan_footprint
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import sha256_file


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    title_screen_mode: str = profile.DEFAULT_TITLE_SCREEN_MODE,
) -> BuildResult:
    """Build the guarded stock-renderer image from one canonical recipe.

    Source authentication remains independent from recipe preparation, and the
    completed output is still verified by raw-image comparison plus read-back
    patch verification.  The recipe only removes duplicate construction of the
    same intended mutations; it does not weaken those trust boundaries.
    """

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(dir=output_directory.parent, prefix=f".{output_directory.name}.")
    )
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            source_ccd,
            temporary,
            profile.OUTPUT_STEM,
            profile.SOURCE_HASHES,
        )
        recipe = prepare_build_recipe(
            title_screen_mode,
            source_image=source_paths[".img"],
        )
        plan = recipe.patch_plan()
        verify_plan_footprint(plan)
        payload_patches = recipe.payload_patches()
        binary_patches = tuple(
            item.payload_patch
            for item in recipe.binary_patches
            if item.payload_patch is not None
        )

        sector_reports = apply_payload_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=profile.TRACK2_START_LBA,
            sector_count=profile.TRACK2_SECTOR_COUNT,
            atomic=False,  # The whole output is already staged transactionally.
        )
        verify_output_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=profile.TRACK2_START_LBA,
        )

        comparison = compare_and_hash_raw_images(source_paths[".img"], output_paths[".img"])
        changed_reports = tuple(
            report for report in sector_reports if report.before_sha256 != report.after_sha256
        )
        expected_lbas = tuple(report.absolute_lba for report in changed_reports)
        if comparison.changed_lbas != expected_lbas:
            raise ValueError(
                "unexpected changed sectors: expected "
                f"{expected_lbas}, found {comparison.changed_lbas}"
            )

        output_hashes = {
            ".ccd": sha256_file(output_paths[".ccd"]),
            ".img": comparison.output_sha256,
            ".sub": sha256_file(output_paths[".sub"]),
        }
        for extension in (".ccd", ".sub"):
            if output_hashes[extension] != profile.SOURCE_HASHES[extension]:
                raise ValueError(f"{extension} changed during build")

        changed_relative_sectors = tuple(report.relative_sector for report in changed_reports)
        guarded_relative_sectors = tuple(report.relative_sector for report in sector_reports)
        if guarded_relative_sectors != recipe.guarded_relative_sectors:
            raise ValueError("mutation engine footprint differs from prepared build recipe")

        manifest = {
            "build_profile": recipe.build_profile,
            "title_screen_mode": recipe.title_screen_mode,
            "patch_plan_sha256": plan.sha256(),
            "scope": (
                "Same-size stock-renderer English vertical slice with guarded text, "
                "layout, profile, Media Mix, and optional title-screen patches; not a "
                "complete translation."
            ),
            "source_hashes": profile.SOURCE_HASHES,
            "output_hashes": output_hashes,
            "image_bytes": output_paths[".img"].stat().st_size,
            "changed_absolute_lbas": list(comparison.changed_lbas),
            "changed_relative_sectors": list(changed_relative_sectors),
            "guarded_relative_sectors": list(guarded_relative_sectors),
            "modified_sectors": [dataclasses.asdict(report) for report in changed_reports],
            "text_patches": text_patch_rows(
                recipe.text_patches,
                sector_size=profile.SECTOR_SIZE,
                track_start_lba=profile.TRACK2_START_LBA,
            ),
            "binary_patches": binary_patch_rows(
                binary_patches,
                sector_size=profile.SECTOR_SIZE,
                track_start_lba=profile.TRACK2_START_LBA,
            ),
            "verification": {
                "source_hashes_match": True,
                "source_text_matches": True,
                "same_size_replacements": True,
                "mode1_edc_ecc_rebuilt": True,
                "only_expected_raw_sectors_changed": True,
                "plan_matches_independent_profile_footprint": True,
                "ccd_unchanged": True,
                "sub_unchanged": True,
                "emulator_boot_tested": False,
            },
        }
        manifest_name = "build_manifest.json"
        (temporary / manifest_name).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        ccd_name = output_paths[".ccd"].name
        (temporary / "HUMAN_TEST_README.txt").write_text(
            profile.build_tester_readme(ccd_name, title_screen_mode),
            encoding="utf-8",
        )
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return BuildResult(
        output_ccd=output_directory / f"{profile.OUTPUT_STEM}.ccd",
        manifest_path=output_directory / manifest_name,
        build_profile=recipe.build_profile,
        title_screen_mode=recipe.title_screen_mode,
        text_patch_count=len(recipe.text_patches),
        binary_patch_count=len(recipe.binary_patches),
        changed_relative_sectors=changed_relative_sectors,
        guarded_relative_sectors=guarded_relative_sectors,
        plan_sha256=plan.sha256(),
    )
