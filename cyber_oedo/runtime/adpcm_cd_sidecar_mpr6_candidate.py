"""Uncertified CD-sidecar variant: execute from MPR6, preserve MPR3.

The source-guarded sidecar is loaded from the CD into Card RAM bank $75,
then executed at $C000 through MPR6. Unlike the previous MPR3 prototype,
no mapping of the game's $6000-$7FFF bank is changed. Audio source uses
bank $6B via MPR5, while the cache tag lives at $C800 inside bank $75
and beyond the one-sector helper image.

This is explicitly a non-release research experiment. An identical ADPCM
target fingerprint is not evidence of street-state parity, code-bank ownership
or audio fidelity. The supported performance builders never import this.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.adpcm_cd_sidecar_candidate import (
    ORIGINAL_ADPCM_LENGTH,
    ORIGINAL_ADPCM_OFFSET,
    ORIGINAL_ADPCM_SHA256,
    ORIGINAL_BIOS_ADPCM_CALL,
    ORIGINAL_BIOS_ADPCM_CALL_OFFSET_IN_FUNCTION,
    SIDECAR_PAYLOAD_OFFSET,
    build_cd_sidecar_stub,
    build_unverified_cd_sidecar_candidate,
)
from cyber_oedo.runtime.card_ram_adpcm_cache import _Assembler


@dataclass(frozen=True, slots=True)
class UncertifiedMpr6CdSidecar:
    patches: tuple[PayloadPatch, ...]
    code_size: int
    extra_disc_reads_per_call: int = 1
    runtime_ownership_certified: bool = False
    audio_fidelity_certified: bool = False
    cross_mission_certified: bool = False
    performance_improved: bool = False
    release_enabled: bool = False


def build_mpr6_adpcm_cache() -> bytes:
    """Historical read-through rewritten to keep executable MPR6 intact."""
    a = _Assembler()
    a.emit(0x43, 0x20, 0x48)
    a.emit(0xA9, 0x6B, 0x53, 0x20)
    a.emit(0xAD, 0x01, 0xC8, 0xC9, 0xA5)
    a.branch(0xD0, "miss")
    a.emit(0xAD, 0x00, 0xC8, 0xCD, 0xDD, 0x8F)
    a.branch(0xD0, "miss")
    a.branch(0x80, "write_adpcm")
    a.label("miss")
    a.emit(0xA9, 4, 0x85, 0xF8, 0x64, 0xF9, 0x64, 0xFA)
    a.emit(0xA9, 0xA0, 0x85, 0xFB, 0xA9, 1, 0x85, 0xFF)
    a.label("read_retry")
    a.emit(0x20, 0x09, 0xE0)
    a.branch(0xD0, "read_retry")
    a.emit(0xAD, 0xDD, 0x8F, 0x8D, 0x00, 0xC8)
    a.emit(0xA9, 0xA5, 0x8D, 0x01, 0xC8)
    a.label("write_adpcm")
    a.emit(0x64, 0xFC, 0xA9, 0xE0, 0x85, 0xFD)
    a.emit(0x64, 0xFA, 0xA9, 0xA0, 0x85, 0xFB)
    a.emit(0x64, 0xF8, 0xA9, 0x20, 0x85, 0xF9)
    a.emit(0x64, 0xFF, 0x20, 0x39, 0xE0)
    a.emit(0xAA, 0x68, 0x53, 0x20, 0x8A, 0x60)
    code = a.finish()
    if len(code) != 85:
        raise ValueError("unexpected MPR6 ADPCM code size")
    return code


def build_mpr6_stub() -> bytes:
    stub = build_cd_sidecar_stub()
    old = bytes.fromhex("43 08 48 A9 75 53 08 20 00 60 68 53 08 60")
    new = bytes.fromhex("43 40 48 A9 75 53 40 20 00 C0 68 53 40 60")
    if stub.count(old) != 1:
        raise ValueError("original stub MPR3 signature mismatch")
    return stub.replace(old, new)


def build_mpr6_sector(original_command: bytes) -> bytes:
    if len(original_command) != ORIGINAL_ADPCM_LENGTH or (
        hashlib.sha256(original_command).hexdigest() != ORIGINAL_ADPCM_SHA256
    ):
        raise ValueError("authenticated original speaker command mismatch")
    pos = ORIGINAL_BIOS_ADPCM_CALL_OFFSET_IN_FUNCTION
    if original_command[pos:pos + 3] != ORIGINAL_BIOS_ADPCM_CALL:
        raise ValueError("original ADPCM transfer signature mismatch")
    command = bytearray(original_command)
    command[pos:pos + 3] = bytes.fromhex("20 38 C0")
    code = bytes(command) + build_mpr6_adpcm_cache()
    if len(code) >= 0x800:
        raise ValueError("sidecar executable overlaps metadata at $C800")
    return code + bytes(2048 - len(code))


def build_unverified_mpr6_cd_sidecar(
    original_payload: bytes, *, acknowledge_unsafe_research: bool = False,
    include_portrait: bool = True,
) -> UncertifiedMpr6CdSidecar:
    """Strict original-source patching; cannot certify ownership or release."""
    old = build_unverified_cd_sidecar_candidate(
        original_payload,
        acknowledge_unsafe_research=acknowledge_unsafe_research,
        include_portrait=include_portrait,
    )
    command = original_payload[
        ORIGINAL_ADPCM_OFFSET:ORIGINAL_ADPCM_OFFSET + ORIGINAL_ADPCM_LENGTH
    ]
    replacements = {
        ORIGINAL_ADPCM_OFFSET: build_mpr6_stub(),
        SIDECAR_PAYLOAD_OFFSET: build_mpr6_sector(command),
    }
    patches = tuple(
        PayloadPatch(
            offset=patch.offset, expected=patch.expected,
            replacement=replacements.get(patch.offset, patch.replacement),
            label=patch.label + " (unverified MPR6 variant)",
        )
        for patch in old.patches
    )
    return UncertifiedMpr6CdSidecar(
        patches=patches, code_size=ORIGINAL_ADPCM_LENGTH + 85
    )
