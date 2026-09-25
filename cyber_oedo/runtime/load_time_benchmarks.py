"""Source-guarded Mission 0 load-time benchmark mutations.

These patches are intentionally independent. They exist to measure which parts
of the stock transition policy dominate latency before any optimization becomes
release behavior.

Benchmarks in this module:

* resident dialogue module: wire the stock JMP-entrypoint probe to skip the
  optical module reload on a cache hit while preserving the cache-miss loader;
* speaker-local retention: stop command 0/5 from invalidating the selector byte
  that already guards the $9000-$9FFF two-sector speaker-local cache;
* short exploration wait: reduce the explicit 120-frame post-fade wait to a
  caller-selected frame count.

None of these are release-enabled. The resident-module benchmark deliberately
does not reset the two known self-modified operand bytes at $8617/$8618; live
profiling must prove that the normal command path reinitializes them safely
before this benchmark can be promoted or strengthened.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    payload_offset_for_lba,
)
from cyber_oedo.runtime.dialogue_residency import (
    MISSION0_B_PAYLOAD_BASE,
    MOVEMENT_AUDIO_FADE_CPU,
    MOVEMENT_MODULE_PAYLOAD_BASE,
)

RESIDENT_LOADER_CPU = 0x48A6
RESIDENT_LOADER_OFFSET = MISSION0_B_PAYLOAD_BASE + RESIDENT_LOADER_CPU
RESIDENT_LOADER_EXPECTED = bytes.fromhex(
    "AD 00 80 0D 03 80 C9 4C A9 00 85 00"
)
RESIDENT_LOADER_REPLACEMENT = bytes.fromhex(
    "AD 00 80 0D 03 80 C9 4C F0 1D 64 00"
)

COMMAND0_CACHE_INVALIDATE_CPU = 0x801E
COMMAND0_CACHE_INVALIDATE_EXPECTED = bytes.fromhex("A9 FF 8D DE 8F")
COMMAND5_CACHE_INVALIDATE_CPU = 0x8155
COMMAND5_CACHE_INVALIDATE_EXPECTED = bytes.fromhex("A9 FF 8D DE 8F")

DIALOGUE_MODULE_PAYLOAD_BASE = payload_offset_for_lba(DIALOGUE_MODULE_LBA)
COMMAND0_CACHE_INVALIDATE_OFFSET = (
    DIALOGUE_MODULE_PAYLOAD_BASE + COMMAND0_CACHE_INVALIDATE_CPU - 0x8000
)
COMMAND5_CACHE_INVALIDATE_OFFSET = (
    DIALOGUE_MODULE_PAYLOAD_BASE + COMMAND5_CACHE_INVALIDATE_CPU - 0x8000
)
CACHE_INVALIDATE_REPLACEMENT = bytes((0xEA,)) * 5

EXPLORATION_WAIT_LDY_CPU = MOVEMENT_AUDIO_FADE_CPU + 5
EXPLORATION_WAIT_LDY_OFFSET = (
    MOVEMENT_MODULE_PAYLOAD_BASE + EXPLORATION_WAIT_LDY_CPU
)
EXPLORATION_WAIT_EXPECTED = bytes.fromhex("A0 78")


@dataclass(frozen=True, slots=True)
class LoadBenchmarkSet:
    name: str
    patches: tuple[PayloadPatch, ...]
    release_enabled: bool = False

    @property
    def changed_bytes(self) -> int:
        return sum(
            sum(
                before != after
                for before, after in zip(
                    patch.expected, patch.replacement, strict=True
                )
            )
            for patch in self.patches
        )


def build_resident_module_benchmark() -> LoadBenchmarkSet:
    """Wire the stock resident check to the stock loader epilogue."""

    return LoadBenchmarkSet(
        name="resident-dialogue-module",
        patches=(
            PayloadPatch(
                offset=RESIDENT_LOADER_OFFSET,
                expected=RESIDENT_LOADER_EXPECTED,
                replacement=RESIDENT_LOADER_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: branch around dialogue-module CD reload "
                    "when both JMP entrypoints are resident"
                ),
            ),
        ),
    )


def build_speaker_cache_retention_benchmark() -> LoadBenchmarkSet:
    """Keep $8FDE valid across command-0/command-5 teardown."""

    return LoadBenchmarkSet(
        name="retain-speaker-local-cache",
        patches=(
            PayloadPatch(
                offset=COMMAND0_CACHE_INVALIDATE_OFFSET,
                expected=COMMAND0_CACHE_INVALIDATE_EXPECTED,
                replacement=CACHE_INVALIDATE_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: preserve speaker-local selector "
                    "$8FDE across command 0"
                ),
            ),
            PayloadPatch(
                offset=COMMAND5_CACHE_INVALIDATE_OFFSET,
                expected=COMMAND5_CACHE_INVALIDATE_EXPECTED,
                replacement=CACHE_INVALIDATE_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: preserve speaker-local selector "
                    "$8FDE across command 5"
                ),
            ),
        ),
    )


def build_short_exploration_wait_benchmark(frames: int = 8) -> LoadBenchmarkSet:
    """Reduce the stock 120-frame exploration transition wait.

    frames must be 1..120. Zero is rejected because LDY #0 would underflow
    through DEY/BNE and wait 256 iterations instead of skipping the delay.
    """

    if not 1 <= frames <= 120:
        raise ValueError("frames must be in 1..120")
    return LoadBenchmarkSet(
        name=f"exploration-wait-{frames}-frames",
        patches=(
            PayloadPatch(
                offset=EXPLORATION_WAIT_LDY_OFFSET,
                expected=EXPLORATION_WAIT_EXPECTED,
                replacement=bytes((0xA0, frames)),
                label=(
                    "Mission 0 benchmark: shorten explicit exploration "
                    f"transition wait from 120 to {frames} frames"
                ),
            ),
        ),
    )


def validate_load_benchmark_sources(payload: bytes) -> dict[str, object]:
    """Validate all benchmark source bytes against the authenticated payload."""

    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    sets = (
        build_resident_module_benchmark(),
        build_speaker_cache_retention_benchmark(),
        build_short_exploration_wait_benchmark(),
    )
    rows = []
    for benchmark in sets:
        rows.append(
            {
                "name": benchmark.name,
                "release_enabled": benchmark.release_enabled,
                "changed_bytes": benchmark.changed_bytes,
                "patches": [
                    {
                        "label": patch.label,
                        "offset": f"0x{patch.offset:08X}",
                        "source_match": (
                            payload[patch.offset : patch.end_offset]
                            == patch.expected
                        ),
                    }
                    for patch in benchmark.patches
                ],
            }
        )
    return {
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "benchmarks": rows,
    }
