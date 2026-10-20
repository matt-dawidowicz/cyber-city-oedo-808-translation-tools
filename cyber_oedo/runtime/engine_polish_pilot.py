"""Make a source-authenticated non-release engine-polish A/B disc.

By default, no performance-altering gameplay patches are installed.
All existing source-guarded Mission-0 cache/restore optimizations remain
explicit, acknowledged UNVERIFIED experiments, never automatic polish.

On a clean-boot Mission-0 NPC, the previous seven-patch combination
failed to reach dialogue; portrait plus ADPCM caching also failed, while
the selective bar restore alone reached the parser. The earlier nine-
patch resident-module shortcut failed in the opening. All are gated.

The optional original authored English VWF diagnostic may be compiled
without enabling ANY of the failing performance candidates.

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


PERFORMANCE_EXPERIMENTS = (
    "none", "portrait", "adpcm", "portrait-adpcm",
    "selective-restore", "all-seven",
)
# The $80E0 hook is in the shared $1425 dialogue module, but its $4CFA
# destination is injected only into the Mission-0-B outer-overlay source.
# A cold-boot watcher NPC replay actually retains this cave and the ADPCM-only
# legacy experiment reaches the watcher; that run DOES NOT establish the
# earlier combined-profile failure's root cause. Other missions' overlay
# residency remains unverified. Quarantine these unverified global redirects
# until a source-guarded bank-safe design and cross-mission live tests exist.
QUARANTINED_ADPCM_PROFILES = frozenset({
    "adpcm", "portrait-adpcm", "all-seven",
})


def build_intro_smoke_polish_patches(performance_experiment: str = "none"):
    """Make an explicitly selected, *uncertified* source-guarded patch set.

    The default remains byte-identical to stock outside independent English
    VWF experimental edits. The six legacy cache/restore candidates are never
    silently promoted after Mesen's clean-boot NPC regression.
    """
    if performance_experiment not in PERFORMANCE_EXPERIMENTS:
        raise ValueError(
            "unknown performance experiment: " + performance_experiment
        )
    if performance_experiment == "none":
        return ()
    if performance_experiment in QUARANTINED_ADPCM_PROFILES:
        raise ValueError(
            "cross-overlay ADPCM residency unverified: the shared LBA $1425 "
            "dialogue module redirects $80E0 into Mission-0-B-only "
            "$4CFA, now reserved by the portrait-cache repair. These "
            "profiles also overlap the portrait patch; unsafe opt-in does "
            "not establish alternate-bank residency or compatibility"
        )
    portrait = build_portrait_cache_benchmark().patches
    adpcm = build_speaker_adpcm_cache_benchmark().patches
    restore = build_selective_bar_vram_restore_benchmark().patches
    options = {
        "portrait": portrait,
        "adpcm": adpcm,
        "portrait-adpcm": portrait + adpcm,
        "selective-restore": restore,
        "all-seven": portrait + adpcm + restore,
    }
    return options[performance_experiment]


def compose_polish_patches(
    original_payload: bytes,
    *,
    english_pilot: bool = False,
    diagnostic_intro: bool = False,
    english: str = "Bartender: Welcome.",
    vwf_pilot: bool = False,
    performance_experiment: str = "none",
    acknowledge_unsafe_performance: bool = False,
):
    """Return nonoverlapping source-matched edits and optional renderer data.

    Never accepts a translated/previously edited payload as original media.
    The test-build path additionally verifies the *entire* Track 2 hash.
    """
    if diagnostic_intro and not english_pilot:
        raise ValueError("diagnostic intro requires --english-pilot")
    if vwf_pilot and not english_pilot:
        raise ValueError("VWF pilot requires --english-pilot")
    if performance_experiment != "none" and not acknowledge_unsafe_performance:
        raise ValueError(
            "untested performance profile requires "
            "--acknowledge-unsafe-performance; see the Mesen NPC regression"
        )
    patches = list(build_intro_smoke_polish_patches(performance_experiment))
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
        runtime = _make_runtime(glyphs, atlas, vwf_loader=vwf_pilot)
        patches.extend(build_m0b_pilot_patches(
            original_payload, glyphs, atlas, english=english,
            diagnostic_intro_redirect=diagnostic_intro,
            vwf_pilot=vwf_pilot,
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
    vwf_pilot: bool = False,
    performance_experiment: str = "none",
    acknowledge_unsafe_performance: bool = False,
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
            vwf_pilot=vwf_pilot,
            performance_experiment=performance_experiment,
            acknowledge_unsafe_performance=acknowledge_unsafe_performance,
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
            "core_patch_count": len(build_intro_smoke_polish_patches(
                performance_experiment
            )),
            "performance_experiment": performance_experiment,
            "performance_runtime_certified": False,
            "performance_regression": (
                "Clean-boot real NPC dialogue failed with all-seven and "
                "portrait-adpcm experiments; never enable automatically"
            ),
            "unsafe_experiment_acknowledged": (
                performance_experiment != "none"
                and acknowledge_unsafe_performance
            ),
            "excluded_regression": (
                "resident-module shortcut: combined Mesen intro produced "
                "invalid-sector retry loop; omitted from safe smoke variant"
            ),
            "observed_scope": (
                "M0B opening VWF and one pre-bartender NPC entry only; "
                "no certified cache/restore performance improvements yet"
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
            "vwf_pilot": vwf_pilot,
            "vwf_authoring": (
                "seamless whole-line 16px cells" if vwf_pilot else None
            ),
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
    parser.add_argument("--vwf-pilot", action="store_true",
                        help="Opt-in VWF cells with --english-pilot")
    parser.add_argument(
        "--performance-experiment", choices=PERFORMANCE_EXPERIMENTS,
        default="none", help="UNSAFE A/B only; default none",
    )
    parser.add_argument(
        "--acknowledge-unsafe-performance", action="store_true",
        help="Required to enable unverified cache/restore mutations",
    )
    parser.add_argument("--diagnostic-intro", action="store_true",
                        help="NON-RELEASE: substitute intro for renderer smoke test")
    args = parser.parse_args(argv)
    ccd = build_polish_disc(
        args.source_ccd, args.output_directory,
        english_pilot=args.english_pilot,
        diagnostic_intro=args.diagnostic_intro,
        vwf_pilot=args.vwf_pilot,
        performance_experiment=args.performance_experiment,
        acknowledge_unsafe_performance=args.acknowledge_unsafe_performance,
    )
    print("output_ccd=" + str(ccd))
    print("release_enabled=false; combined_runtime_certified=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
