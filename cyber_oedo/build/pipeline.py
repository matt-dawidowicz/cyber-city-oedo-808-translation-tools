"""Orchestrate the authenticated human-test build with efficient I/O."""

from __future__ import annotations

import dataclasses
import datetime
import json
import pathlib
import shutil
import tempfile

from cyber_oedo.build import engine
from cyber_oedo.build.image_verify import (
    compare_and_hash_raw_images,
    verify_output_patches,
)
from cyber_oedo.build.manifest import binary_patch_rows, text_patch_rows
from cyber_oedo.build.source import resolve_source_set
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import sha256_file


def _copy_clonecd_set(
    source_paths: dict[str, pathlib.Path],
    temporary: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """Copy the authenticated source set under the test-build stem."""

    outputs: dict[str, pathlib.Path] = {}
    for extension, source in source_paths.items():
        destination = temporary / f"{engine.OUTPUT_STEM}{extension}"
        shutil.copy2(source, destination)
        outputs[extension] = destination
    return outputs


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    title_screen_mode: str = engine.DEFAULT_TITLE_SCREEN_MODE,
) -> pathlib.Path:
    """Build the guarded stock-renderer image with consolidated checks."""

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(
            f"output directory already exists: {output_directory}"
        )
    source_paths = resolve_source_set(source_ccd, engine.SOURCE_HASHES)
    title_patches = engine.optional_title_screen_patches(
        source_paths[".img"],
        title_screen_mode,
    )
    text_patches = tuple(
        patch.to_payload_patch()
        for patch in engine.HUMAN_TEST_PATCHES
    )
    binary_patches = engine.HUMAN_TEST_BINARY_PATCHES + title_patches
    payload_patches = text_patches + binary_patches

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(
            dir=output_directory.parent,
            prefix=f".{output_directory.name}.",
        )
    )
    try:
        output_paths = _copy_clonecd_set(source_paths, temporary)
        sector_reports = apply_payload_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=engine.TRACK2_START_LBA,
            sector_count=engine.TRACK2_SECTOR_COUNT,
        )
        verify_output_patches(
            output_paths[".img"],
            payload_patches,
            start_lba=engine.TRACK2_START_LBA,
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
        expected_lbas = tuple(
            report.absolute_lba
            for report in changed_reports
        )
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
            if output_hashes[extension] != engine.SOURCE_HASHES[extension]:
                raise ValueError(f"{extension} changed during build")

        manifest = {
            "build_profile": engine.BUILD_PROFILE,
            "title_screen_mode": title_screen_mode,
            "created_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "scope": (
                "Same-size stock-renderer English vertical slice with "
                "guarded text, layout, profile, Media Mix, and optional "
                "title-screen patches; not a complete translation."
            ),
            "source_hashes": engine.SOURCE_HASHES,
            "output_hashes": output_hashes,
            "image_bytes": output_paths[".img"].stat().st_size,
            "changed_absolute_lbas": list(comparison.changed_lbas),
            "changed_relative_sectors": [
                report.relative_sector
                for report in changed_reports
            ],
            "guarded_relative_sectors": [
                report.relative_sector
                for report in sector_reports
            ],
            "modified_sectors": [
                dataclasses.asdict(report)
                for report in changed_reports
            ],
            "text_patches": text_patch_rows(
                engine.HUMAN_TEST_PATCHES,
                sector_size=engine.SECTOR_SIZE,
                track_start_lba=engine.TRACK2_START_LBA,
            ),
            "binary_patches": binary_patch_rows(
                binary_patches,
                sector_size=engine.SECTOR_SIZE,
                track_start_lba=engine.TRACK2_START_LBA,
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
            engine.build_tester_readme(ccd_name, title_screen_mode),
            encoding="utf-8",
        )
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return output_directory / f"{engine.OUTPUT_STEM}.ccd"
