"""Build KURUZER resource-relocation test discs for emulator certification.

Two diagnostic modes, neither release-enabled:

``move``
    Relink the unchanged 800-byte KURUZER resource into the owned linker
    window and repoint its descriptor.  The game must behave exactly as stock.
``grow``
    Relink KURUZER with the opening narration played twice (1,494 bytes).
    The narration must show both copies and the following location caption
    and scene must still run, proving later commands do not depend on fixed
    offsets inside the resource.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import tempfile
from collections.abc import Sequence

from cyber_oedo.build.image_verify import compare_and_hash_raw_images, verify_output_patches
from cyber_oedo.build.profiles import mission0_stock as stock_profile
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload
from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.named_resources import find_descriptor, parse_mission0_b_descriptors
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.disc.resource_linker import relink_named_resource
from cyber_oedo.resources.kuruzer import (
    KURUZER_NAME,
    KURUZER_OBSERVED_LOAD_ADDRESS,
    authenticate_kuruzer,
    doubled_narration_record,
    rebuild_kuruzer,
)

BUILD_PROFILE = "kuruzer-relocation-test"
MODES = ("move", "grow")
TRACK2_PAYLOAD_SHA256 = "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"


def output_stem(mode: str) -> str:
    return f"Cyber City Oedo 808 - Kemono no Alignment (Japan) [KURUZER {mode} test]"


def kuruzer_relink(payload: bytes, mode: str):
    """Return the relink plan for *mode* against an authenticated payload."""

    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    descriptor = find_descriptor(parse_mission0_b_descriptors(payload), KURUZER_NAME)
    start = descriptor.resource_payload_offset
    resource = payload[start : start + descriptor.byte_length]
    authenticate_kuruzer(resource)
    data = resource if mode == "move" else rebuild_kuruzer(resource, doubled_narration_record(resource))
    return relink_named_resource(
        payload, descriptor, data, load_address=KURUZER_OBSERVED_LOAD_ADDRESS
    )


def build_relocation_test(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    mode: str,
) -> pathlib.Path:
    """Build one guarded test disc in a staged directory, published atomically."""

    stem = output_stem(mode)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(
        tempfile.mkdtemp(dir=output_directory.parent, prefix=f".{output_directory.name}.")
    )
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            source_ccd, temporary, stem, stock_profile.SOURCE_HASHES
        )
        payload_path = temporary / "track02_mode1_2048.bin"
        _, payload_sha = extract_mode1_payload(
            source_paths[".img"], payload_path,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )
        if payload_sha != TRACK2_PAYLOAD_SHA256:
            raise ValueError(f"Track 2 payload hash mismatch: {payload_sha}")
        payload = payload_path.read_bytes()
        relink = kuruzer_relink(payload, mode)

        reports = apply_payload_patches(
            output_paths[".img"], relink.patches,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
            atomic=False,  # The whole output directory is staged.
        )
        verify_output_patches(output_paths[".img"], relink.patches, start_lba=TRACK2_START_LBA)
        comparison = compare_and_hash_raw_images(source_paths[".img"], output_paths[".img"])
        expected = tuple(r.absolute_lba for r in reports if r.before_sha256 != r.after_sha256)
        if comparison.changed_lbas != expected:
            raise ValueError(
                f"unexpected changed sectors: expected {expected}, found {comparison.changed_lbas}"
            )

        linked = relink.linked
        manifest = {
            "build_profile": BUILD_PROFILE,
            "mode": mode,
            "release_enabled": False,
            "resource": KURUZER_NAME,
            "descriptor_payload_offset": f"0x{relink.descriptor.payload_offset:08X}",
            "original_lba": f"0x{relink.descriptor.absolute_lba:04X}",
            "original_length": relink.descriptor.byte_length,
            "relinked_lba": f"0x{linked.start_sector:04X}",
            "relinked_relative_sector": relink.relative_sector,
            "relinked_span": linked.sector_span,
            "relinked_length": linked.byte_length,
            "observed_load_address": f"0x{KURUZER_OBSERVED_LOAD_ADDRESS:04X}",
            "descriptor_tail": relink.descriptor_tail.hex(" ").upper(),
            "changed_absolute_lbas": list(comparison.changed_lbas),
            "output_img_sha256": comparison.output_sha256,
            "patches": [
                {"offset": f"0x{patch.offset:08X}", "bytes": len(patch.replacement), "label": patch.label}
                for patch in relink.patches
            ],
        }
        (temporary / "relocation_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        payload_path.unlink()
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_directory / f"{stem}.ccd"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a KURUZER relocation test disc (diagnostic, not release-enabled)."
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument("--mode", choices=MODES, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = build_relocation_test(args.source_ccd, args.output_directory, args.mode)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"output_ccd={output}")
    print(f"profile={BUILD_PROFILE} mode={args.mode}")
    return 0
