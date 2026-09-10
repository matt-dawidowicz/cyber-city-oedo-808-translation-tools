"""Orchestrate the authenticated human-test build with efficient I/O."""

from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib
import shutil
import tempfile

from cyber_oedo.build.profiles import mission0_stock as profile
from cyber_oedo.build.image_verify import (
    compare_and_hash_raw_images,
    verify_output_patches,
)
from cyber_oedo.build.manifest import binary_patch_rows, text_patch_rows
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import sha256_file


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    title_screen_mode: str = profile.DEFAULT_TITLE_SCREEN_MODE,
) -> pathlib.Path:
    """Build the guarded stock-renderer image with consolidated checks."""

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(
            dir=output_directory.parent,
            prefix=f".{output_directory.name}.",
        )
    )
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            source_ccd,
            temporary,
            profile.OUTPUT_STEM,
            profile.SOURCE_HASHES,
        )
        title_patches = profile.optional_title_screen_patches(
            source_paths[".img"],
            title_screen_mode,
        )
        text_patches = tuple(
            patch.to_payload_patch() for patch in profile.HUMAN_TEST_PATCHES
        )
        binary_patches = profile.HUMAN_TEST_BINARY_PATCHES + title_patches
        payload_patches = text_patches + binary_patches

        sector_reports = apply_payload_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=profile.TRACK2_START_LBA,
            sector_count=profile.TRACK2_SECTOR_COUNT,
        )
        verify_output_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=profile.TRACK2_START_LBA,
        )

        comparison = compare_and_hash_raw_images(
            source_paths[".img"],
            output_paths[".img"],
        )
        changed_reports = tuple(
            report
            for report in sector_reports
            if report.before_sha256 != report.after_sha256
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

        manifest = {
            "build_profile": profile.BUILD_PROFILE,
            "title_screen_mode": title_screen_mode,
            "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "scope": (
                "Same-size stock-renderer English vertical slice with "
                "guarded text, layout, profile, Media Mix, and optional "
                "title-screen patches; not a complete translation."
            ),
            "source_hashes": profile.SOURCE_HASHES,
            "output_hashes": output_hashes,
            "image_bytes": output_paths[".img"].stat().st_size,
            "changed_absolute_lbas": list(comparison.changed_lbas),
            "changed_relative_sectors": [
                report.relative_sector for report in changed_reports
            ],
            "guarded_relative_sectors": [
                report.relative_sector for report in sector_reports
            ],
            "modified_sectors": [
                dataclasses.asdict(report) for report in changed_reports
            ],
            "text_patches": text_patch_rows(
                profile.HUMAN_TEST_PATCHES,
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
                "ccd_unchanged": True,
                "sub_unchanged": True,
                "emulator_boot_tested": False,
            },
        }
        (temporary / "build_manifest.json").write_text(
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

    return output_directory / f"{profile.OUTPUT_STEM}.ccd"
