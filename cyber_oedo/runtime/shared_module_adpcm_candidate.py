"""FAIL-CLOSED Mission-0-B shared-dialogue-tail ADPCM research candidate.

This prototype relocates the *historical* 95-byte ADPCM cache from the
collision at $4CFA to the source-zero tail of the M0B dialogue module
at $8F51. The M0B loader is extended from $0F51 to $0FB0 bytes.

IMPORTANT: source-zero tail is NOT authenticated runtime ownership. The
module tail lies in BSS space and may be read/written by runtime features or
other overlays. No ADPCM-containing production profile may call this module.
This module deliberately refuses to produce patches without an explicit
unsafe_research-only acknowledgment. Even that does not certify the design.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.card_ram_adpcm_cache import (
    ADPCM_CALL_EXPECTED,
    ADPCM_CALL_OFFSET,
    build_speaker_adpcm_cache_cave,
)
from cyber_oedo.runtime.card_ram_portrait_cache import (
    PORTRAIT_CACHE_CAVE_CPU,
    PORTRAIT_CACHE_CAVE_REPLACEMENT,
    build_portrait_cache_benchmark,
)
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    DIALOGUE_MODULE_LENGTH,
    DIALOGUE_MODULE_LOADER_BYTES,
    DIALOGUE_MODULE_LOADER_CPU,
    MISSION0_B_PAYLOAD_BASE,
    payload_offset_for_lba,
)

TAIL_CODE_CPU = 0x8F51
TAIL_CODE_SOURCE_OFFSET = payload_offset_for_lba(DIALOGUE_MODULE_LBA) + DIALOGUE_MODULE_LENGTH
TAIL_LAST_UNCLAIMED_CPU = 0x8FDC  # $8FDD is the active speaker selector
SOURCE_LOADER_BYTE_COUNT = DIALOGUE_MODULE_LENGTH  # $0F51
LOADER_LENGTH_LOW_BYTE_OFFSET = (
    MISSION0_B_PAYLOAD_BASE
    + DIALOGUE_MODULE_LOADER_CPU
    + DIALOGUE_MODULE_LOADER_BYTES.index(bytes.fromhex("A9 51 85 06"))
    + 1
)
ADPCM_TAIL_CODE = build_speaker_adpcm_cache_cave()
EXTENDED_MODULE_BYTES = SOURCE_LOADER_BYTE_COUNT + len(ADPCM_TAIL_CODE)
assert len(ADPCM_TAIL_CODE) == 95
assert TAIL_CODE_CPU + len(ADPCM_TAIL_CODE) - 1 <= TAIL_LAST_UNCLAIMED_CPU
assert EXTENDED_MODULE_BYTES == 0x0FB0
assert TAIL_CODE_CPU > 0x8000


@dataclass(frozen=True, slots=True)
class UnverifiedDialogueTailCandidate:
    patches: tuple[PayloadPatch, ...]
    runtime_ownership_certified: bool = False
    audio_fidelity_certified: bool = False
    cross_overlay_certified: bool = False
    release_enabled: bool = False


def build_unverified_dialogue_tail_candidate(
    *,
    unsafe_research: bool = False,
    authenticated_payload: bytes | None = None,
) -> UnverifiedDialogueTailCandidate:
    """Build original-source-only patches for a *disposable* combined specimen.

    Does not mutate source media. No invocation from production engine builders.
    A full source payload, when supplied, must pass the full Track-2 digest and
    exact source-byte checks; mismatch or previously patched input fails closed.
    """
    if not unsafe_research:
        raise ValueError(
            "refusing unverified dialogue-module BSS ownership: "
            "isolated unsafe_research=True required (not release certification)"
        )

    patches = (
        *build_portrait_cache_benchmark().patches,
        PayloadPatch(
            offset=ADPCM_CALL_OFFSET,
            expected=ADPCM_CALL_EXPECTED,
            replacement=bytes((0x20, TAIL_CODE_CPU & 0xFF, TAIL_CODE_CPU >> 8)),
            label="UNSAFE research: M0B ADPCM call -> module-tail $8F51",
        ),
        PayloadPatch(
            offset=TAIL_CODE_SOURCE_OFFSET,
            expected=bytes(len(ADPCM_TAIL_CODE)),
            replacement=ADPCM_TAIL_CODE,
            label="UNSAFE research: module-tail ADPCM code (unproved BSS ownership)",
        ),
        PayloadPatch(
            offset=LOADER_LENGTH_LOW_BYTE_OFFSET,
            expected=bytes((SOURCE_LOADER_BYTE_COUNT & 0xFF,)),
            replacement=bytes((EXTENDED_MODULE_BYTES & 0xFF,)),
            label="UNSAFE research: extend M0B module loader only",
        ),
    )
    ordered = tuple(sorted(patches, key=lambda patch: patch.offset))
    for left, right in zip(ordered, ordered[1:]):
        if left.end_offset > right.offset:
            raise ValueError(f"overlapping candidate source patches: {left.label} / {right.label}")
    # Explicit structural guard against silently repurposing the portrait cave.
    assert TAIL_CODE_CPU != PORTRAIT_CACHE_CAVE_CPU
    assert len(PORTRAIT_CACHE_CAVE_REPLACEMENT) == 103

    if authenticated_payload is not None:
        if hashlib.sha256(authenticated_payload).hexdigest() != TRACK2_PAYLOAD_SHA256:
            raise ValueError("authenticated Track-2 source digest mismatch")
        for patch in ordered:
            if authenticated_payload[patch.offset:patch.end_offset] != patch.expected:
                raise ValueError(f"source-byte mismatch: {patch.label}")

    return UnverifiedDialogueTailCandidate(patches=ordered)
