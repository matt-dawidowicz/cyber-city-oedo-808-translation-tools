"""Source-guarded Mission 0 speaker-ADPCM Card-RAM read-through benchmark.

Dialogue command 1 has already resolved the active speaker ADPCM LBA into
$FC/$FE/$FD before JSR $E033 at $80E0.  This benchmark redirects that call to
an outer-overlay cave.  The cave caches the current 8 KiB speaker ADPCM source
in Super System Card bank $6B and uses the game's proven local-memory
AD_WRITE $E039 path to populate ADPCM RAM $E000.

The tag lives in the 0xAF-byte metadata slack after the planned module +
speaker-local image in bank $6C.  A hit is keyed by the Mission-0 speaker
selector at $8FDD.  Misses use ordinary local CD_READ and therefore fail back
onto real optical I/O rather than trusting stale cache bytes.

The benchmark depends on the Mission 0 B outer overlay remaining mapped at
$4CFA. This historical placement now overlaps with the experimentally
repaired portrait cache, and these two legacy benchmarks must not be combined.
The natural watcher confirms the old ADPCM-only cave was present there, but
later-scene residency and overall runtime behavior remain unverified.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    MISSION0_B_PAYLOAD_BASE,
    payload_offset_for_lba,
)

ADPCM_CALL_CPU = 0x80E0
ADPCM_CALL_OFFSET = payload_offset_for_lba(DIALOGUE_MODULE_LBA) + (
    ADPCM_CALL_CPU - 0x8000
)
ADPCM_CALL_EXPECTED = bytes.fromhex("20 33 E0")

ADPCM_CACHE_CAVE_CPU = 0x4CFA
ADPCM_CACHE_CAVE_OFFSET = MISSION0_B_PAYLOAD_BASE + ADPCM_CACHE_CAVE_CPU

ADPCM_CACHE_BANK = 0x6B
METADATA_BANK = 0x6C
SPEAKER_TAG_ADDRESS = 0xDF51
SPEAKER_TAG_MAGIC_ADDRESS = 0xDF52
SPEAKER_TAG_MAGIC = 0xA5


class _Assembler:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.branches: list[tuple[int, str]] = []

    def emit(self, *values: int) -> None:
        self.code.extend(values)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def branch(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0)
        self.branches.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand_index, label in self.branches:
            delta = self.labels[label] - (operand_index + 1)
            if not -128 <= delta <= 127:
                raise ValueError(f"branch to {label} is out of range")
            self.code[operand_index] = delta & 0xFF
        return bytes(self.code)


def build_speaker_adpcm_cache_cave() -> bytes:
    a = _Assembler()

    # Preserve MPR5/MPR6, then map audio source + metadata banks.
    a.emit(0x43, 0x20, 0x48)
    a.emit(0x43, 0x40, 0x48)
    a.emit(0xA9, ADPCM_CACHE_BANK, 0x53, 0x20)
    a.emit(0xA9, METADATA_BANK, 0x53, 0x40)

    # Valid only when magic and the active Mission-0 speaker selector match.
    a.emit(0xAD, SPEAKER_TAG_MAGIC_ADDRESS & 0xFF, SPEAKER_TAG_MAGIC_ADDRESS >> 8)
    a.emit(0xC9, SPEAKER_TAG_MAGIC)
    a.branch(0xD0, "miss")
    a.emit(0xAD, SPEAKER_TAG_ADDRESS & 0xFF, SPEAKER_TAG_ADDRESS >> 8)
    a.emit(0xCD, 0xDD, 0x8F)
    a.branch(0xD0, "miss")
    a.branch(0x80, "write_adpcm")

    a.label("miss")
    # Four sectors -> logical $A000 in Card RAM through ordinary CD_READ.
    a.emit(0xA9, 0x04, 0x85, 0xF8)
    a.emit(0x64, 0xF9)
    a.emit(0x64, 0xFA)
    a.emit(0xA9, 0xA0, 0x85, 0xFB)
    a.emit(0xA9, 0x01, 0x85, 0xFF)
    a.label("read_retry")
    a.emit(0x20, 0x09, 0xE0)
    a.branch(0xD0, "read_retry")
    a.emit(0xAD, 0xDD, 0x8F)
    a.emit(0x8D, SPEAKER_TAG_ADDRESS & 0xFF, SPEAKER_TAG_ADDRESS >> 8)
    a.emit(0xA9, SPEAKER_TAG_MAGIC)
    a.emit(0x8D, SPEAKER_TAG_MAGIC_ADDRESS & 0xFF, SPEAKER_TAG_MAGIC_ADDRESS >> 8)

    a.label("write_adpcm")
    # Existing AD_WRITE contract: CX=ADPCM, BX=local memory, AX=length, DH=0.
    a.emit(0x64, 0xFC)
    a.emit(0xA9, 0xE0, 0x85, 0xFD)
    a.emit(0x64, 0xFA)
    a.emit(0xA9, 0xA0, 0x85, 0xFB)
    a.emit(0x64, 0xF8)
    a.emit(0xA9, 0x20, 0x85, 0xF9)
    a.emit(0x64, 0xFF)
    a.emit(0x20, 0x39, 0xE0)

    # Preserve BIOS result while restoring mappings; stock $80E3 checks A.
    a.emit(0xAA)
    a.emit(0x68, 0x53, 0x40)
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x8A, 0x60)
    return a.finish()


ADPCM_CACHE_CAVE_REPLACEMENT = build_speaker_adpcm_cache_cave()
ADPCM_CACHE_CAVE_EXPECTED = bytes(len(ADPCM_CACHE_CAVE_REPLACEMENT))
ADPCM_CALL_REPLACEMENT = bytes(
    (0x20, ADPCM_CACHE_CAVE_CPU & 0xFF, ADPCM_CACHE_CAVE_CPU >> 8)
)


@dataclass(frozen=True, slots=True)
class SpeakerAdpcmCacheBenchmark:
    patches: tuple[PayloadPatch, ...]

    @property
    def changed_bytes(self) -> int:
        return sum(
            before != after
            for patch in self.patches
            for before, after in zip(patch.expected, patch.replacement, strict=True)
        )


def build_speaker_adpcm_cache_benchmark() -> SpeakerAdpcmCacheBenchmark:
    return SpeakerAdpcmCacheBenchmark(
        patches=(
            PayloadPatch(
                offset=ADPCM_CALL_OFFSET,
                expected=ADPCM_CALL_EXPECTED,
                replacement=ADPCM_CALL_REPLACEMENT,
                label="Mission 0 benchmark: redirect speaker AD_TRANS to Card-RAM cache",
            ),
            PayloadPatch(
                offset=ADPCM_CACHE_CAVE_OFFSET,
                expected=ADPCM_CACHE_CAVE_EXPECTED,
                replacement=ADPCM_CACHE_CAVE_REPLACEMENT,
                label="Mission 0 benchmark: install speaker ADPCM read-through cave",
            ),
        )
    )
