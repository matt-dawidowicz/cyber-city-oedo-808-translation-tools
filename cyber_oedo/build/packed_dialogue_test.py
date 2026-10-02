"""Build a Mission 0 packed-English dialogue test disc from the final master."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import tempfile
from collections import Counter
from collections.abc import Sequence

from cyber_oedo.build.profiles import mission0_stock as stock_profile
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload
from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.packed_english_runtime import (
    build_runtime,
    compact_repertoire_for_texts,
    runtime_payload_patches,
)
from cyber_oedo.text.final_dialogue_insertion import (
    FINAL_DIALOGUE_MASTER_SHA256,
    audit_rows,
    build_in_place_patches,
    load_final_dialogue_tsv,
    summarize_audit,
)
from cyber_oedo.text.font_atlas import RasterConfig, rasterize_atlas
from cyber_oedo.text.packed_english import PackedEnglishDictionary

BUILD_PROFILE = "mission0-packed-final-dialogue-test"
OUTPUT_STEM = "Cyber City Oedo 808 - Kemono no Alignment (Japan) [Packed Dialogue Test]"
TRACK2_PAYLOAD_SHA256 = "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"

def build_packed_dialogue_test(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    final_dialogue_tsv: pathlib.Path,
    font_path: pathlib.Path,
    *,
    point_size: int = 13,
    threshold: int = 96,
) -> pathlib.Path:
    """Build a guarded Mission 0 disc with final packed-English dialogue."""
    if sha256_file(final_dialogue_tsv) != FINAL_DIALOGUE_MASTER_SHA256:
        raise ValueError("final-dialogue TSV SHA-256 does not match the reviewed master")
    rows = load_final_dialogue_tsv(final_dialogue_tsv)
    english = tuple(row.english for row in rows)
    repertoire = compact_repertoire_for_texts(english)
    dictionary = PackedEnglishDictionary.from_texts(english, repertoire=repertoire)
    atlas = rasterize_atlas(
        font_path,
        repertoire.characters,
        config=RasterConfig(point_size=point_size, threshold=threshold),
    )
    runtime = build_runtime(dictionary, atlas)

    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = pathlib.Path(tempfile.mkdtemp(
        dir=output_directory.parent, prefix=f".{output_directory.name}."
    ))
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            source_ccd, temporary, OUTPUT_STEM, stock_profile.SOURCE_HASHES
        )
        payload_path = temporary / "track02_mode1_2048.bin"
        _, payload_sha = extract_mode1_payload(
            source_paths[".img"], payload_path,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )
        if payload_sha != TRACK2_PAYLOAD_SHA256:
            raise ValueError(f"Track 2 payload hash mismatch: {payload_sha}")
        payload = payload_path.read_bytes()
        audits = audit_rows(payload, rows, dictionary)
        dialogue_patches = build_in_place_patches(
            payload,
            rows,
            dictionary,
            allowed_banks=frozenset({"MISSION_0"}),
            allow_padding_candidates=False,
        )
        patches = runtime_payload_patches(runtime) + dialogue_patches
        reports = apply_payload_patches(
            output_paths[".img"], patches,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )

        status_counts = Counter(audit.status for audit in audits if audit.row.bank == "MISSION_0")
        relocation = [
            {
                "id": audit.row.entry_id,
                "bank": audit.row.bank,
                "resource": audit.row.resource,
                "offset": f"0x{audit.row.offset:08X}",
                "source_bytes": audit.source_bytes,
                "packed_bytes": audit.packed_bytes,
                "status": audit.status,
                "detail": audit.detail,
            }
            for audit in audits
            if audit.row.bank == "MISSION_0" and not audit.can_patch_exactly
        ]
        manifest = {
            "build_profile": BUILD_PROFILE,
            "final_dialogue_tsv_sha256": FINAL_DIALOGUE_MASTER_SHA256,
            "font_sha256": atlas.source_sha256,
            "font_point_size": point_size,
            "font_threshold": threshold,
            "pair_dictionary": dictionary.utilization_report(),
            "runtime_layout": runtime.layout_report(),
            "mission0_audit": dict(sorted(status_counts.items())),
            "mission0_inserted_rows": len(dialogue_patches),
            "runtime_patch_count": len(runtime_payload_patches(runtime)),
            "changed_relative_sectors": sorted({r.relative_sector for r in reports if r.before_sha256 != r.after_sha256}),
            "full_master_audit": summarize_audit(audits),
            "release_enabled": False,
        }
        (temporary / "packed_dialogue_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (temporary / "mission0_relocation_queue.json").write_text(
            json.dumps(relocation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        payload_path.unlink()
        temporary.replace(output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output_directory / f"{OUTPUT_STEM}.ccd"

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Mission 0 with the reviewed packed-English dialogue master."
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument("final_dialogue_tsv", type=pathlib.Path)
    parser.add_argument("font", type=pathlib.Path)
    parser.add_argument("--point-size", type=int, default=13)
    parser.add_argument("--threshold", type=int, default=96)
    return parser

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = build_packed_dialogue_test(
            args.source_ccd, args.output_directory, args.final_dialogue_tsv, args.font,
            point_size=args.point_size, threshold=args.threshold,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"output_ccd={output}")
    print("profile=" + BUILD_PROFILE)
    print("release_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
