"""Create an isolated CloneCD test for the Stage 1 English escape stream.

The input is the existing stock-renderer human-test build, not the immutable
Japanese disc.  This derivative is intentionally separate and only changes a
single early dialogue field plus three source-guarded executable ranges.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import hashlib
import json
import pathlib
import shutil
import tempfile

from build_human_test_disc import (
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
    compare_raw_images,
    verify_output_text,
)
from cdrom_mode1 import PayloadPatch, apply_payload_patches
from wide_runtime_stage1 import (
    WIDE_END,
    WIDE_START,
    build_stage1_runtime_patches,
    encode_stage1_field,
)


BUILD_PROFILE = "wide-engine-stage1-tagged-escape"
OUTPUT_STEM = (
    "Cyber City Oedo 808 - Kemono no Alignment (Japan) "
    "[Wide Engine Stage 1 Escape Test]"
)
TEST_TEXT = "WIDE ENGINE ESCAPE TEST X"
TEST_OFFSET = 0x00145892
TEST_FOOTPRINT = 28


def hash_file(path: pathlib.Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_clonecd_set(source_ccd: pathlib.Path) -> dict[str, pathlib.Path]:
    """Resolve a complete matching-stem CloneCD set from its descriptor."""

    resolved = source_ccd.resolve()
    if resolved.suffix.lower() != ".ccd":
        raise ValueError("source path must name a .ccd file")
    paths = {
        extension: resolved.with_suffix(extension)
        for extension in (".ccd", ".img", ".sub")
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("missing CloneCD companion: " + ", ".join(missing))
    return paths


def stage1_payload_patches() -> tuple[PayloadPatch, ...]:
    """Return the exact runtime and visible-dialogue patches for Stage 1."""

    runtime = tuple(
        PayloadPatch(
            offset=patch.payload_offset,
            expected=patch.expected,
            replacement=patch.replacement,
            label=patch.label,
        )
        for patch in build_stage1_runtime_patches()
    )
    source_field = bytes.fromhex(
        "82618281829282948146814082768285828c8283828f828d82858144"
    )
    replacement = encode_stage1_field(TEST_TEXT, TEST_FOOTPRINT)
    text_patch = PayloadPatch(
        offset=TEST_OFFSET,
        expected=source_field,
        replacement=replacement,
        label="Stage 1 Mission 0 bartender escape-stream proof",
    )
    return runtime + (text_patch,)


def copy_clonecd_set(
    source_paths: dict[str, pathlib.Path],
    destination: pathlib.Path,
) -> dict[str, pathlib.Path]:
    """Copy the source set under the distinct Stage 1 output stem."""

    copied: dict[str, pathlib.Path] = {}
    for extension, source in source_paths.items():
        target = destination / f"{OUTPUT_STEM}{extension}"
        shutil.copy2(source, target)
        copied[extension] = target
    return copied


def tester_readme(ccd_name: str) -> str:
    """Return concise manual-test instructions for the isolated test disc."""

    return "\n".join(
        (
            "Cyber City Oedo 808 - Wide Engine Stage 1 Escape Test",
            "=======================================================",
            "",
            "Purpose",
            "-------",
            "This is an experimental derivative of the stock-renderer "
            "test disc.",
            "It tests one FF 00 ... FE literal-ASCII dialogue stream in "
            "Mission 0.",
            "It does NOT yet implement 8x16 glyphs or 22 visible columns.",
            "",
            "How to test",
            "-----------",
            f"1. Open {ccd_name} in a PC Engine CD emulator.",
            "2. Use a Japanese System Card 3.0 BIOS and begin Mission 0.",
            "3. Reach the first bartender dialogue at the beginning of "
            "the mission.",
            "4. Expected text: WIDE ENGINE ESCAPE TEST X.",
            "5. It may wrap at the original 11 fullwidth cells; that is "
            "expected.",
            "6. Continue through the first scene, open/close a menu, then "
            "restart.",
            "",
            "Pass criteria",
            "-------------",
            "- The disc boots and reaches the bartender scene.",
            "- The expected letters are readable in order.",
            "- No blank dialog, random glyphs, border stripes, jitter, or "
            "crash.",
            "- Normal Japanese and stock English outside the test line "
            "remain normal.",
            "",
            "Stop criteria",
            "-------------",
            "Stop testing and report a screenshot/clip if boot, dialogue, "
            "or redraw changes.",
            (
                "Stop if menu, audio, or restart behavior changes. "
                "This is not a save-safe release build."
            ),
            "",
            "Evidence to report",
            "------------------",
            "- Emulator and BIOS version.",
            "- Full-screen screenshot or 10-20 second video of the target "
            "line.",
            "- Whether the scene, menu, audio, and restart passed or failed.",
            "- The build_manifest.json SHA-256 values.",
            "",
        )
    )


def build_stage1_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
) -> pathlib.Path:
    """Copy, patch, and structurally verify a new Stage 1 CloneCD set."""

    destination = output_directory.resolve()
    if destination.exists():
        raise ValueError(f"output directory already exists: {destination}")
    source_paths = resolve_clonecd_set(source_ccd)
    source_hashes = {
        extension: hash_file(path) for extension, path in source_paths.items()
    }
    patches = stage1_payload_patches()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
        )
    )
    try:
        output_paths = copy_clonecd_set(source_paths, temporary)
        reports = apply_payload_patches(
            output_paths[".img"],
            patches,
            start_lba=TRACK2_START_LBA,
            sector_count=TRACK2_SECTOR_COUNT,
        )
        verify_output_text(output_paths[".img"], patches)
        changed_lbas = compare_raw_images(
            source_paths[".img"], output_paths[".img"]
        )
        changed_reports = tuple(
            report for report in reports
            if report.before_sha256 != report.after_sha256
        )
        expected_lbas = tuple(
            report.absolute_lba for report in changed_reports
        )
        if changed_lbas != expected_lbas:
            raise ValueError(
                f"unexpected changed sectors: expected {expected_lbas}, "
                f"found {changed_lbas}"
            )
        output_hashes = {
            extension: hash_file(path)
            for extension, path in output_paths.items()
        }
        for extension in (".ccd", ".sub"):
            if output_hashes[extension] != source_hashes[extension]:
                raise ValueError(f"{extension} changed during Stage 1 build")
        manifest = {
            "build_profile": BUILD_PROFILE,
            "created_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
            "base_build": "core-interaction-dialogue-clean-2026-07-28",
            "scope": (
                "Stage 1 FF 00 tagged ASCII escape parser and stock 16x16 "
                "glyph adapter. Not an 8x16 renderer or release candidate."
            ),
            "test_text": TEST_TEXT,
            "test_text_offset": f"0x{TEST_OFFSET:08X}",
            "source_hashes": source_hashes,
            "output_hashes": output_hashes,
            "changed_absolute_lbas": list(changed_lbas),
            "modified_sectors": [
                dataclasses.asdict(report) for report in changed_reports
            ],
            "patches": [
                {
                    "offset": f"0x{patch.offset:08X}",
                    "label": patch.label,
                    "expected_sha256": hashlib.sha256(
                        patch.expected
                    ).hexdigest(),
                    "replacement_sha256": hashlib.sha256(
                        patch.replacement
                    ).hexdigest(),
                }
                for patch in patches
            ],
            "verification": {
                "source_bytes_match": True,
                "same_size_replacements": True,
                "mode1_edc_ecc_rebuilt": True,
                "only_expected_raw_sectors_changed": True,
                "ccd_unchanged": True,
                "sub_unchanged": True,
                "emulator_tested": False,
                "safe_for_saves": False,
            },
        }
        (temporary / "build_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (temporary / "HUMAN_TEST_README.txt").write_text(
            tester_readme(output_paths[".ccd"].name), encoding="utf-8"
        )
        temporary.replace(destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination / f"{OUTPUT_STEM}.ccd"


def main() -> None:
    """Parse build arguments and print the completed Stage 1 descriptor."""

    parser = argparse.ArgumentParser(
        description="Create an isolated Stage 1 wide-engine escape test disc."
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    arguments = parser.parse_args()
    try:
        output_ccd = build_stage1_disc(
            arguments.source_ccd,
            arguments.output_directory,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"output_ccd={output_ccd}")
    print(f"profile={BUILD_PROFILE}")
    print("structural_validation=passed")
    print("human_emulator_test=pending")


if __name__ == "__main__":
    main()
