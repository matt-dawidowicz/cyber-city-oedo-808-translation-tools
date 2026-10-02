"""Compose the independently guarded Mission 0 bar fast-load benchmarks.

The core stack contains only mutations with an existing correctness argument or
stock fallback:
* fail-closed resident dialogue-module reuse;
* speaker-local retention is deliberately NOT in the default core because its
  physical lifetime across the $22DE exploration load is still unresolved;
* portrait Card-RAM read-through;
* speaker ADPCM Card-RAM read-through;
* native two-span bar VRAM restore.

The counter-gated setup-VSync bypass and hard audio teardown remain optional
aggressive A/B experiments and are not included by default.

The separate 120-frame movement-overlay benchmark is intentionally excluded:
the live bartender/bar overlay uses a different 30-frame transition path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.card_ram_adpcm_cache import (
    build_speaker_adpcm_cache_benchmark,
)
from cyber_oedo.runtime.card_ram_portrait_cache import build_portrait_cache_benchmark
from cyber_oedo.runtime.fast_fade_benchmark import build_fast_fade_benchmark_patch
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.load_time_benchmarks import (
    build_dialogue_setup_vsync_benchmark,
    build_resident_module_benchmark,
    build_selective_bar_vram_restore_benchmark,
    build_speaker_cache_retention_benchmark,
)


@dataclass(frozen=True, slots=True)
class CombinedBarBenchmark:
    name: str
    patches: tuple[PayloadPatch, ...]
    aggressive: bool

    def assert_non_overlapping(self) -> None:
        ordered = sorted(self.patches, key=lambda item: item.offset)
        for left, right in zip(ordered, ordered[1:]):
            if left.end_offset > right.offset:
                raise ValueError(
                    f"overlapping patches: {left.label!r} and {right.label!r}"
                )

    @property
    def changed_bytes(self) -> int:
        return sum(
            before != after
            for patch in self.patches
            for before, after in zip(patch.expected, patch.replacement, strict=True)
        )


def _extend(rows: list[PayloadPatch], benchmark: object) -> None:
    patches = getattr(benchmark, "patches", None)
    if patches is not None:
        rows.extend(patches)
        return
    patch = getattr(benchmark, "patch", None)
    if patch is None:
        raise TypeError("benchmark exposes neither patches nor patch")
    rows.append(patch)


def build_combined_bar_benchmark(
    *,
    aggressive: bool = False,
    include_lifetime_sensitive_speaker_retention: bool = False,
) -> CombinedBarBenchmark:
    rows: list[PayloadPatch] = []
    for benchmark in (
        build_resident_module_benchmark(),
        build_portrait_cache_benchmark(),
        build_speaker_adpcm_cache_benchmark(),
        build_selective_bar_vram_restore_benchmark(),
    ):
        _extend(rows, benchmark)

    if include_lifetime_sensitive_speaker_retention:
        _extend(rows, build_speaker_cache_retention_benchmark())

    if aggressive:
        _extend(rows, build_dialogue_setup_vsync_benchmark())
        _extend(rows, build_fast_fade_benchmark_patch())

    result = CombinedBarBenchmark(
        name=(
            "mission0-bar-fast-load-aggressive"
            if aggressive
            else "mission0-bar-fast-load-core"
        ),
        patches=tuple(rows),
        aggressive=aggressive,
    )
    result.assert_non_overlapping()
    return result


def validate_combined_bar_sources(
    payload: bytes,
    *,
    aggressive: bool = False,
    include_lifetime_sensitive_speaker_retention: bool = False,
) -> dict[str, object]:
    """Validate the authenticated payload and every composed source guard."""

    result = build_combined_bar_benchmark(
        aggressive=aggressive,
        include_lifetime_sensitive_speaker_retention=(
            include_lifetime_sensitive_speaker_retention
        ),
    )
    digest = hashlib.sha256(payload).hexdigest()
    rows = []
    for patch in result.patches:
        actual = payload[patch.offset : patch.end_offset]
        rows.append(
            {
                "label": patch.label,
                "offset": f"0x{patch.offset:08X}",
                "bytes": len(patch.expected),
                "source_match": actual == patch.expected,
            }
        )
    return {
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "benchmark": result.name,
        "patch_count": len(result.patches),
        "all_source_guards_match": all(row["source_match"] for row in rows),
        "patches": rows,
        "release_enabled": False,
    }
