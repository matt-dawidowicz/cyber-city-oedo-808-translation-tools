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
  caller-selected frame count;
* selective bar VRAM restore: replace the stock one-shot $EE00-byte restore
  with two source-guarded BIOS CD-to-VRAM calls that skip untouched sectors.

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

BAR_RESTORE_CALL_OFFSET = 0x00A4442E
BAR_RESTORE_CALL_EXPECTED = bytes.fromhex("20 59 44 60")
BAR_RESTORE_CALL_REPLACEMENT = bytes.fromhex("4C 1C A3 EA")

BAR_PRIMARY_DESCRIPTOR_OFFSET = 0x00A6D30D
BAR_PRIMARY_DESCRIPTOR_EXPECTED = bytes.fromhex("00 E8 22 00 EE")
BAR_PRIMARY_DESCRIPTOR_REPLACEMENT = bytes.fromhex("00 E8 22 20 8E")

BAR_SELECTIVE_CAVE_OFFSET = 0x00A6D31C
BAR_SELECTIVE_CAVE_EXPECTED = bytes(33)
BAR_SELECTIVE_CAVE_REPLACEMENT = bytes.fromhex(
    "20 59 44 "          # JSR $4459: first shortened stock transfer
    "AD 10 37 "          # LDA $3710: scene descriptor index
    "D0 13 "             # BNE -> RTS for non-bar scene variants
    "A9 38 85 02 "       # descriptor pointer low = $38
    "A9 A3 85 03 "       # descriptor pointer high = $A3
    "A9 00 85 00 "       # destination VRAM word low = $00
    "A9 6D 85 01 "       # destination VRAM word high = $6D
    "20 59 44 "          # JSR $4459: second transfer
    "60 "                # RTS
    "00 01 23 00 1A"     # LBA $2301, byte length $1A00
)


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


def build_selective_bar_vram_restore_benchmark() -> LoadBenchmarkSet:
    """Benchmark the measured two-span bar VRAM restore.

    The stock routine calls $4459 once and returns. This benchmark redirects
    that return through zero-filled scene-table padding at $A31C. The cave
    performs the shortened original transfer, checks $3710 so non-bar scene
    variants do not receive the extra call, then performs LBA $2301 -> VRAM
    word $6D00 for $1A00 bytes through the same stock loader.

    This remains benchmark-only until zero-padding ownership and broader
    room/dialogue coverage are release-certified.
    """

    return LoadBenchmarkSet(
        name="selective-bar-vram-restore",
        patches=(
            PayloadPatch(
                offset=BAR_RESTORE_CALL_OFFSET,
                expected=BAR_RESTORE_CALL_EXPECTED,
                replacement=BAR_RESTORE_CALL_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: redirect bar scene VRAM restore "
                    "through selective two-span trampoline"
                ),
            ),
            PayloadPatch(
                offset=BAR_PRIMARY_DESCRIPTOR_OFFSET,
                expected=BAR_PRIMARY_DESCRIPTOR_EXPECTED,
                replacement=BAR_PRIMARY_DESCRIPTOR_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: shorten bar $22E8 VRAM transfer "
                    "from $EE00 to $8E20 bytes"
                ),
            ),
            PayloadPatch(
                offset=BAR_SELECTIVE_CAVE_OFFSET,
                expected=BAR_SELECTIVE_CAVE_EXPECTED,
                replacement=BAR_SELECTIVE_CAVE_REPLACEMENT,
                label=(
                    "Mission 0 benchmark: install bar selective VRAM "
                    "trampoline and $2301/$1A00 second descriptor"
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
        build_selective_bar_vram_restore_benchmark(),
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
