"""Make a source-authenticated non-release engine-polish A/B disc.

This deliberately composes *existing* source-guarded Mission-0
fast-load benchmark patches, not a new mechanic: portrait/ADPCM
Card-RAM read-through and selective bar VRAM restoration.

An earlier nine-patch combination including resident-module reuse
FAILED an actual Mesen prologue replay (invalid-sector reads). Excluding
that two-patch module shortcut restored the original $7B intro path.
The suspect shortcut is NOT part of this build.

A separately opt-in English pilot can share the disc. Aggressive audio
hard cuts and unproved VSync shortcuts are NEVER included.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import tempfile

from cyber_oedo.build.profiles.mission0_stock import SOURCE_HASHES
from cyber_oedo.build.source import copy_authenticated_source_set
from cyber_oedo.disc.clonecd_cue import build_cue
from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload
from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.runtime.card_ram_portrait_cache import (
    build_portrait_cache_benchmark,
)
from cyber_oedo.runtime.card_ram_adpcm_cache import (
    build_speaker_adpcm_cache_benchmark,
)
from cyber_oedo.runtime.load_time_benchmarks import (
    build_selective_bar_vram_restore_benchmark,
)
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256

OUTPUT_STEM = "Cyber City Oedo 808 [M0 Engine Polish Experimental]"
ENGLISH_POOL_BANKS = "$7C-$7F"
CACHE_BANKS = "$68-$6C"


def build_intro_smoke_polish_patches():
    """Source-pinned independent candidates; excludes failing resident hook."""
    return tuple(
        patch
        for benchmark in (
            build_portrait_cache_benchmark(),
            build_speaker_adpcm_cache_benchmark(),
            build_selective_bar_vram_restore_benchmark(),
        )
        for patch in benchmark.patches
    )


def compose_polish_patches(
    original_payload: bytes,
    *,
    english_pilot: bool = False,
    diagnostic_intro: bool = False,
    english: str = "Bartender: Welcome.",
):
    """Return nonoverlapping source-matched edits and optional renderer data.

    Never accepts a translated/previously edited payload as original media.
    The test-build path additionally verifies the *entire* Track 2 hash.
    """
    if diagnostic_intro and not english_pilot:
        raise ValueError("diagnostic intro requires --english-pilot")
    patches = list(build_intro_smoke_polish_patches())
    runtime = None
    atlas = None
    if english_pilot:
        from cyber_oedo.runtime.mission0_pool_pilot import (
            _make_runtime, build_m0b_pilot_patches,
        )
        from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
        from cyber_oedo.text.oedo_pixel_font import authored_atlas

        glyphs = EnglishGlyphTable.from_texts((english, " ?"))
        atlas = authored_atlas(glyphs.characters)
        runtime = _make_runtime(glyphs, atlas)
        patches.extend(build_m0b_pilot_patches(
            original_payload, glyphs, atlas, english=english,
            diagnostic_intro_redirect=diagnostic_intro,
        ))

    patches.sort(key=lambda x: x.offset)
    for patch in patches:
        if original_payload[patch.offset:patch.end_offset] != patch.expected:
            raise ValueError(
                f"{patch.label}: authenticated source signature mismatch "
                f"at 0x{patch.offset:08X}"
            )
    for before, after in zip(patches, patches[1:]):
        if before.end_offset > after.offset:
            raise ValueError(
                f"overlapping source patches: {before.label} / {after.label}"
            )
    return tuple(patches), runtime, atlas


def build_polish_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    english_pilot: bool = False,
    diagnostic_intro: bool = False,
    english: str = "Bartender: Welcome.",
) -> pathlib.Path:
    """Create a fresh authenticated 88-track test copy, never a release build."""
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError("output directory exists; refusing to overwrite it")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temp = pathlib.Path(tempfile.mkdtemp(
        prefix="oedo-engine-polish.", dir=output_directory.parent
    ))
    try:
        _, destinations = copy_authenticated_source_set(
            source_ccd, temp, OUTPUT_STEM, SOURCE_HASHES
        )
        track2 = temp / "track02_mode1_original.bin"
        byte_count, digest = extract_mode1_payload(
            destinations[".img"], track2,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )
        if (
            byte_count != TRACK2_SECTOR_COUNT * 2048
            or digest != TRACK2_PAYLOAD_SHA256
        ):
            raise ValueError("source Track 2 hash/size mismatch")
        patches, runtime, atlas = compose_polish_patches(
            track2.read_bytes(),
            english_pilot=english_pilot,
            diagnostic_intro=diagnostic_intro,
            english=english,
        )
        reports = apply_payload_patches(
            destinations[".img"], patches,
            start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT,
        )
        cue = temp / f"{OUTPUT_STEM}.cue"
        build_cue(destinations[".ccd"], cue)
        report = {
            "profile": "M0-ENGINE-POLISH-A-B-NON-RELEASE",
            "source_payload_sha256": digest,
            "audio_policy": "unchanged: no hard cut or fade-time bypass",
            "gameplay_policy": "unchanged: no casefile/saves/new interactions",
            "added_features": [],
            "core_patch_count": len(build_intro_smoke_polish_patches()),
            "excluded_regression": (
                "resident-module shortcut: combined Mesen intro produced "
                "invalid-sector retry loop; omitted from safe smoke variant"
            ),
            "observed_scope": (
                "M0B opening boot and $7B diagnostic only; "
                "not yet certified in bar, other rooms or later missions"
            ),
            "patch_count": len(patches),
            "changed_sectors": sorted(
                r.relative_sector for r in reports
                if r.before_sha256 != r.after_sha256
            ),
            "patches": [{
                "offset": f"0x{p.offset:08X}",
                "length": len(p.expected),
                "label": p.label,
                "expected_sha256": hashlib.sha256(p.expected).hexdigest(),
                "replacement_sha256": hashlib.sha256(p.replacement).hexdigest(),
            } for p in patches],
            "english_pilot": english_pilot,
            "english_font_sha256": atlas.source_sha256 if atlas else None,
            "diagnostic_intro": diagnostic_intro,
            "card_ram_core": CACHE_BANKS,
            "card_ram_english": ENGLISH_POOL_BANKS if english_pilot else None,
            "live_combination_certified": False,
            "natural_bartender_certified": False,
            "text_vwf_live_certified": False,
            "room_and_mission_coverage_certified": False,
            "release_enabled": False,
        }
        (temp / "engine_polish_manifest.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if runtime is not None:
            from cyber_oedo.runtime.mission0_pool_pilot import (
                render_pilot_mesen_trace,
            )
            (temp / "mesen_english_pool_trace.lua").write_text(
                render_pilot_mesen_trace(runtime.labels), encoding="utf-8"
            )
        track2.unlink()
        temp.replace(output_directory)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return output_directory / (OUTPUT_STEM + ".ccd")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument("--english-pilot", action="store_true",
                        help="Include existing opt-in English bartender proof")
    parser.add_argument("--diagnostic-intro", action="store_true",
                        help="NON-RELEASE: substitute intro for renderer smoke test")
    args = parser.parse_args(argv)
    ccd = build_polish_disc(
        args.source_ccd, args.output_directory,
        english_pilot=args.english_pilot,
        diagnostic_intro=args.diagnostic_intro,
    )
    print("output_ccd=" + str(ccd))
    print("release_enabled=false; combined_runtime_certified=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
