"""Build a Mission 0 packed-English dialogue test disc from the final master."""

from __future__ import annotations

import argparse
import hashlib
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
from cyber_oedo.runtime.opening_menu import (
    DEFAULT_MENU_AUDIO_TRACK,
    build_opening_menu_patches,
)
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

def load_mission0b_evidence(
    path: pathlib.Path | None,
    rows: Sequence[object],
) -> frozenset[str]:
    """Require per-row overlay evidence before patching an M0-B-only renderer.

    Workbook bank `MISSION_0` cannot tell whether a dialogue uses M0-A or
    M0-B. This is a deliberate opt-in gate, NOT automated runtime proof.
    Missing/unknown entries and an unauthenticated source are rejected.
    """
    if path is None:
        raise ValueError(
            "M0-B packed dialogue requires --mission0b-evidence with "
            "individual runtime traces; MISSION_0 alone is insufficient"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Mission 0-B evidence must be a JSON object")
    if raw.get("source_payload_sha256") != TRACK2_PAYLOAD_SHA256:
        raise ValueError("Mission 0-B evidence references the wrong source payload")
    if raw.get("runtime_overlay") != "MISSION_0_B":
        raise ValueError("Mission 0-B evidence must identify MISSION_0_B explicitly")
    ids = raw.get("entry_ids")
    traces = raw.get("runtime_traces")
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(item, str) or not item for item in ids)
        or len(ids) != len(set(ids))
    ):
        raise ValueError("Mission 0-B evidence needs unique nonempty entry IDs")
    if not isinstance(traces, dict):
        raise ValueError("Mission 0-B evidence needs per-entry runtime_traces")
    known = {row.entry_id: row for row in rows}
    for entry_id in ids:
        row = known.get(entry_id)
        if row is None or row.bank != "MISSION_0":
            raise ValueError(f"{entry_id}: not a known Mission 0 dialogue row")
        if not isinstance(traces.get(entry_id), str) or not traces[entry_id].strip():
            raise ValueError(f"{entry_id}: M0-B runtime trace reference is missing")
    return frozenset(ids)


def optional_opening_menu_patches(
    payload: bytes,
    *,
    enable: bool,
    audio_track: int,
) -> tuple:
    """Enable the source-guarded opening menu only on explicit request."""
    if not enable:
        return ()
    return build_opening_menu_patches(payload, audio_track=audio_track)


def verify_nonoverlapping_patches(patches: tuple) -> None:
    spans = sorted(
        (patch.offset, patch.offset + len(patch.expected), patch.label)
        for patch in patches
    )
    for previous, current in zip(spans, spans[1:]):
        if current[0] < previous[1]:
            raise ValueError(
                "overlapping source patches: "
                f"{previous[2]} and {current[2]}"
            )


def build_packed_dialogue_test(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    final_dialogue_tsv: pathlib.Path,
    font_path: pathlib.Path,
    *,
    mission0b_evidence: pathlib.Path | None = None,
    include_definitive_menu: bool = False,
    menu_audio_track: int = DEFAULT_MENU_AUDIO_TRACK,
    point_size: int = 13,
    threshold: int = 96,
) -> pathlib.Path:
    """Build a guarded, M0-B-evidence-limited historical packed-English disc."""
    if sha256_file(final_dialogue_tsv) != FINAL_DIALOGUE_MASTER_SHA256:
        raise ValueError("final-dialogue TSV SHA-256 does not match the reviewed master")
    rows = load_final_dialogue_tsv(final_dialogue_tsv)
    proven_m0b_ids = load_mission0b_evidence(mission0b_evidence, rows)
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
            allowed_entry_ids=proven_m0b_ids,
            allow_padding_candidates=False,
        )
        menu_patches = optional_opening_menu_patches(
            payload,
            enable=include_definitive_menu,
            audio_track=menu_audio_track,
        )
        patches = runtime_payload_patches(runtime) + dialogue_patches + menu_patches
        verify_nonoverlapping_patches(patches)
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
            "mission0b_evidence_entry_count": len(proven_m0b_ids),
            "mission0b_evidence_sha256": hashlib.sha256(
                mission0b_evidence.read_bytes()
            ).hexdigest(),
            "mission0_uncertified_rows_skipped": (
                sum(audit.row.bank == "MISSION_0" and audit.row.entry_id not in proven_m0b_ids
                    for audit in audits)
            ),
            "opening_menu_enabled": include_definitive_menu,
            "opening_menu_audio_track": menu_audio_track if include_definitive_menu else None,
            "opening_menu_patch_count": len(menu_patches),
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
    parser.add_argument(
        "--mission0b-evidence", type=pathlib.Path, required=True,
        help="JSON mapping selected dialogue IDs to observed MISSION_0_B runtime traces",
    )
    parser.add_argument("--definitive-menu", action="store_true")
    parser.add_argument("--menu-audio-track", type=int, default=DEFAULT_MENU_AUDIO_TRACK)
    parser.add_argument("--point-size", type=int, default=13)
    parser.add_argument("--threshold", type=int, default=96)
    return parser

def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        output = build_packed_dialogue_test(
            args.source_ccd, args.output_directory, args.final_dialogue_tsv, args.font,
            mission0b_evidence=args.mission0b_evidence,
            include_definitive_menu=args.definitive_menu,
            menu_audio_track=args.menu_audio_track,
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
