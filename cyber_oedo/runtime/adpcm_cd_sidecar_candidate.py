"""Separate CD-sector ADPCM helper / Card RAM bank $75 (UNSAFE RESEARCH).

The disc has ample tail sectors, but HuC6280 code needs owned EXECUTABLE RAM.
Replace exactly the 56-byte stock $80AF..$80E6 command body with a 55-byte
loader, and move the stock command + historical cache to a *dedicated* 2048-byte
source-zero CD sector. Reload into Card RAM bank $75 on EVERY use and execute
via temporarily mapped MPR3. This is a correctness/proof candidate, not yet
an optimization: it adds one physical CD_READ per ADPCM call, and the bank,
BIOS retry, interrupt and cross-overlay contracts are not fully certified.
Neither $4CFA (occupied portrait cave) nor $8F51 (live game code) is reused.

No ordinary release or unsafe performance build imports this module.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.disc.game_layout import (
    TRACK2_SECTOR_COUNT, TRACK2_START_LBA, SECTOR_SIZE,
)
from cyber_oedo.runtime.card_ram_adpcm_cache import build_speaker_adpcm_cache_cave
from cyber_oedo.runtime.card_ram_portrait_cache import build_portrait_cache_benchmark
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA, payload_offset_for_lba,
)

SIDECAR_RELATIVE_SECTOR = 41190
SIDECAR_LBA = TRACK2_START_LBA + SIDECAR_RELATIVE_SECTOR
SIDECAR_PAYLOAD_OFFSET = SIDECAR_RELATIVE_SECTOR * SECTOR_SIZE
SIDECAR_CARD_RAM_BANK = 0x75
SIDECAR_EXEC_CPU = 0x6000
ORIGINAL_ADPCM_CPU = 0x80AF
ORIGINAL_ADPCM_LENGTH = 0x38
ORIGINAL_ADPCM_OFFSET = payload_offset_for_lba(DIALOGUE_MODULE_LBA) + (
    ORIGINAL_ADPCM_CPU - 0x8000
)
ORIGINAL_ADPCM_SHA256 = (
    "941661178b27f0054919b55f0853bc0842563c2c0618e1f756f6492cbb45de61"
)
ORIGINAL_BIOS_ADPCM_CALL_OFFSET_IN_FUNCTION = 0x31
ORIGINAL_BIOS_ADPCM_CALL = bytes.fromhex("20 33 E0")


@dataclass(frozen=True, slots=True)
class AdpcmCdSidecarCandidate:
    patches: tuple[PayloadPatch, ...]
    sidecar_code_bytes: int
    extra_disc_reads_per_invocation: int = 1
    release_enabled: bool = False
    private_card_ram_bank_ownership_certified: bool = False
    all_overlay_residency_certified: bool = False
    audio_fidelity_certified: bool = False
    performance_improved: bool = False


def build_cd_sidecar_stub() -> bytes:
    """Source-owned 56-byte HuC6280 function becomes a sidecar loader."""
    code = bytearray()
    def emit(*v: int) -> None:
        code.extend(v)
    # Copy original bank mapping on stack, map executable physical bank for
    # local-memory CD_READ at logical $A000.
    emit(0x43, 0x20, 0x48)
    emit(0xA9, SIDECAR_CARD_RAM_BANK, 0x53, 0x20)
    assert SIDECAR_LBA >> 16 == 0
    # BIOS LBA registers: $FC=high, $FE=low, $FD=middle.
    emit(0x64, 0xFC)
    emit(0xA9, SIDECAR_LBA & 0xFF, 0x85, 0xFE)
    emit(0xA9, SIDECAR_LBA >> 8 & 0xFF, 0x85, 0xFD)
    emit(0xA9, 0x01, 0x85, 0xF8, 0x85, 0xFF)
    emit(0x64, 0xF9, 0x64, 0xFA)
    emit(0xA9, 0xA0, 0x85, 0xFB)
    emit(0x20, 0x09, 0xE0)  # CD_READ, exact 1 sector.
    emit(0xAA, 0x68, 0x53, 0x20, 0x8A)  # recover read result after restoring MPR5.
    branch_index = len(code)
    emit(0xD0, 0x00)  # BNE -> retry; stock code also loops on I/O errors.
    emit(0x43, 0x08, 0x48)  # preserve MPR3.
    emit(0xA9, SIDECAR_CARD_RAM_BANK, 0x53, 0x08)
    emit(0x20, 0x00, 0x60)  # relocate stock routine to $6000.
    emit(0x68, 0x53, 0x08, 0x60)  # restore MPR3; return to game.
    delta = -(branch_index + 2)
    if not -128 <= delta <= 127:
        raise ValueError("bootstrap retry branch out of range")
    code[branch_index + 1] = delta & 0xFF
    if len(code) > ORIGINAL_ADPCM_LENGTH:
        raise ValueError("sidecar loader cannot fit stock routine body")
    return bytes(code) + bytes([0xEA]) * (ORIGINAL_ADPCM_LENGTH - len(code))


def build_cd_sidecar_sector(original_function: bytes) -> bytes:
    """Relocate the full stock command and append historic ADPCM cache."""
    if len(original_function) != ORIGINAL_ADPCM_LENGTH or (
        hashlib.sha256(original_function).hexdigest() != ORIGINAL_ADPCM_SHA256
    ):
        raise ValueError("authenticated original ADPCM routine signature mismatch")
    pos = ORIGINAL_BIOS_ADPCM_CALL_OFFSET_IN_FUNCTION
    if original_function[pos:pos + 3] != ORIGINAL_BIOS_ADPCM_CALL:
        raise ValueError("stock AD_TRANS signature mismatch")
    historical_cache = build_speaker_adpcm_cache_cave()
    if len(historical_cache) != 95:
        raise ValueError("historical ADPCM cache size changed")
    relocated = bytearray(original_function)
    routine = SIDECAR_EXEC_CPU + len(original_function)
    relocated[pos:pos + 3] = bytes((0x20, routine & 0xFF, routine >> 8))
    sidecar = bytes(relocated) + historical_cache
    if len(sidecar) > SECTOR_SIZE:
        raise ValueError("code exceeds source-guarded CD sector")
    return sidecar + bytes(SECTOR_SIZE - len(sidecar))


def build_unverified_cd_sidecar_candidate(
    original_payload: bytes, *, acknowledge_unsafe_research: bool = False,
    include_portrait: bool = True,
) -> AdpcmCdSidecarCandidate:
    """Return source-matched, nonoverlapping patches for disposable tests."""
    if not acknowledge_unsafe_research:
        raise ValueError("isolated unsafe research acknowledgment required")
    if hashlib.sha256(original_payload).hexdigest() != TRACK2_PAYLOAD_SHA256:
        raise ValueError("authenticated source Track 2 digest mismatch")
    if len(original_payload) != TRACK2_SECTOR_COUNT * SECTOR_SIZE:
        raise ValueError("Track 2 length mismatch")
    original = original_payload[
        ORIGINAL_ADPCM_OFFSET:ORIGINAL_ADPCM_OFFSET + ORIGINAL_ADPCM_LENGTH
    ]
    zero_sector = original_payload[
        SIDECAR_PAYLOAD_OFFSET:SIDECAR_PAYLOAD_OFFSET + SECTOR_SIZE
    ]
    if zero_sector != bytes(SECTOR_SIZE):
        raise ValueError("reserved CD sidecar sector not source-zero")
    patches = (
        PayloadPatch(
            offset=ORIGINAL_ADPCM_OFFSET, expected=original,
            replacement=build_cd_sidecar_stub(),
            label="UNSAFE: source-owned command redirected to private CD bank",
        ),
        PayloadPatch(
            offset=SIDECAR_PAYLOAD_OFFSET, expected=bytes(SECTOR_SIZE),
            replacement=build_cd_sidecar_sector(original),
            label="UNSAFE: private bank ADPCM CD sidecar",
        ),
    ) + (build_portrait_cache_benchmark().patches if include_portrait else ())
    ordered = tuple(sorted(patches, key=lambda p: p.offset))
    for p in ordered:
        if original_payload[p.offset:p.end_offset] != p.expected:
            raise ValueError("source-byte mismatch: " + p.label)
    for previous, following in zip(ordered, ordered[1:]):
        if previous.end_offset > following.offset:
            raise ValueError("overlapping research patch regions")
    return AdpcmCdSidecarCandidate(
        patches=ordered, sidecar_code_bytes=ORIGINAL_ADPCM_LENGTH + 95
    )
