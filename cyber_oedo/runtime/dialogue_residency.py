"""Source-guarded dialogue residency and audio-transition architecture.

Mission 0 deliberately packs its dialogue runtime into one 8 KiB CD-RAM bank:
module code/data at $8000-$8F50, a 0xAF-byte BSS gap at $8F51-$8FFF,
and a 0x1000-byte speaker-local block at $9000-$9FFF.

The stock module loader probes the two JMP entrypoints at $8000/$8003 before
reloading, but no conditional branch consumes the comparison. The Mission 0
module is self-modifying; a control-flow walk of known entrypoints finds only
$8617/$8618 inside the source-loaded body are modified. They are the operand of
the LDA $0000 instruction at $8616. This module documents that architecture; it
does not enable a cache mutation.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    DIALOGUE_MODULE_LENGTH,
    DIALOGUE_MODULE_SHA256,
    payload_offset_for_lba,
)

MISSION0_B_PAYLOAD_BASE = 0x00131800
MISSION0_MODULE_LOADER_CPU = 0x489E
MISSION0_MODULE_LOADER_LENGTH = 0x33
MISSION0_MODULE_LOADER_SHA256 = (
    "08631f757736aa7cf7a01f0cff92745f38dadc51e45ce084b24a1fbb66552e13"
)

RESIDENT_CHECK = bytes.fromhex("AD 00 80 0D 03 80 C9 4C")
STANDARD_RESIDENT_LOADER_PREFIX = bytes.fromhex(
    "AD 00 80 0D 03 80 C9 4C "
    "A9 00 85 00 A9 80 85 01 A9 00 85 02"
)
EXPECTED_STANDARD_LOADERS = 11
EXPECTED_ALL_RESIDENT_CHECKS = 12

MODULE_CPU_START = 0x8000
MODULE_CPU_END_EXCLUSIVE = MODULE_CPU_START + DIALOGUE_MODULE_LENGTH
MODULE_BSS_START = MODULE_CPU_END_EXCLUSIVE
MODULE_BSS_END_EXCLUSIVE = 0x9000
MODULE_BSS_BYTES = MODULE_BSS_END_EXCLUSIVE - MODULE_BSS_START
SPEAKER_LOCAL_START = 0x9000
SPEAKER_LOCAL_END_EXCLUSIVE = 0xA000
SPEAKER_LOCAL_BYTES = SPEAKER_LOCAL_END_EXCLUSIVE - SPEAKER_LOCAL_START

MODULE_MUTABLE_CPU_BYTES = (0x8617, 0x8618)
MODULE_IMMUTABLE_SHA256 = (
    "c0b71dfb04f32db00dac4c7e1de7372c14173884c7dfd3970c439609da5360f1"
)

SELF_MOD_WRITE_SITES = (
    (0x829E, 0x8D, 0x8617), (0x82A4, 0x8D, 0x8618),
    (0x82D2, 0xEE, 0x8617), (0x82D7, 0xEE, 0x8618),
    (0x82FA, 0xEE, 0x8617), (0x82FF, 0xEE, 0x8618),
    (0x8306, 0xCE, 0x8617), (0x830F, 0xCE, 0x8618),
    (0x8319, 0xEE, 0x8617), (0x831E, 0xEE, 0x8618),
    (0x8327, 0xEE, 0x8617), (0x832C, 0xEE, 0x8618),
    (0x8339, 0x8D, 0x8617), (0x8342, 0x8D, 0x8618),
    (0x8356, 0xEE, 0x8617), (0x835B, 0xEE, 0x8618),
    (0x8364, 0xEE, 0x8617), (0x8369, 0xEE, 0x8618),
    (0x8373, 0x8D, 0x8617), (0x837C, 0x8D, 0x8618),
    (0x8389, 0xEE, 0x8617), (0x838E, 0xEE, 0x8618),
    (0x8602, 0x8D, 0x8617), (0x8608, 0x8D, 0x8618),
)

MODULE_COMMAND_REGION_LENGTH = 0x168
MODULE_COMMAND_REGION_SHA256 = (
    "4ffc842beffb555b08bd1c64bfb97dbc7f54a4d2a99465eeb77e88b833fff026"
)
MODULE_UPDATE_CPU = 0x8229
MODULE_UPDATE_LENGTH = 0x2E
MODULE_UPDATE_SHA256 = (
    "b7eebcdb7cc52c6169f3b20aa9f2262abf285f947dff5197d44283e2ac1f94cf"
)

OUTER_EXIT_CPU = 0x4198
OUTER_EXIT_LENGTH = 0x68
OUTER_EXIT_SHA256 = (
    "8209e3e8779e5bea70be110fdfe8a1181765acf31bfad83495557167e3f5ea7e"
)

MOVEMENT_MODULE_PAYLOAD_BASE = 0x000A4800
MOVEMENT_EXIT_CPU = 0x402B
MOVEMENT_EXIT_LENGTH = 0xBE
MOVEMENT_EXIT_SHA256 = (
    "feb4ac222a1067d35eccf020c5cf097c1075923408fdc2aeadc4b20788f26b08"
)
MOVEMENT_AUDIO_FADE_CPU = 0x40DB
MOVEMENT_AUDIO_FADE_BYTES = bytes.fromhex(
    "A9 0C 20 2D E0 A0 78 20 7B E0 88 D0 FA 60"
)

VOICE_DESCRIPTOR_CPU = 0x8BA3
VOICE_DESCRIPTOR_COUNT = 157
VOICE_DESCRIPTOR_BYTES = VOICE_DESCRIPTOR_COUNT * 6
VOICE_DESCRIPTOR_SHA256 = (
    "3dff96b6bb5aa6bd46dfc2f4265fa401eb0e45c1038f2690f797382d500e903e"
)


@dataclass(frozen=True, slots=True)
class VoiceDescriptor:
    selector: int
    lba: int
    sectors: int
    parameter_word: int

    @property
    def end_lba_exclusive(self) -> int:
        return self.lba + self.sectors


@dataclass(frozen=True, slots=True)
class ResidentLoader:
    payload_offset: int
    lba: int
    byte_length: int
    loader_entry: int

    @property
    def sectors_touched(self) -> int:
        return (self.byte_length + 0x7FF) // 0x800


def _find_all(data: bytes, needle: bytes) -> tuple[int, ...]:
    hits: list[int] = []
    cursor = 0
    while True:
        found = data.find(needle, cursor)
        if found < 0:
            return tuple(hits)
        hits.append(found)
        cursor = found + 1


def _decode_standard_loader(payload: bytes, offset: int) -> ResidentLoader:
    blob = payload[offset : offset + 0x2B]
    if not blob.startswith(STANDARD_RESIDENT_LOADER_PREFIX):
        raise ValueError("not a standard resident loader")

    expected = (
        (20, 0xA9, 22, 0x85, 23, 0x04),
        (24, 0xA9, 26, 0x85, 27, 0x05),
        (28, 0xA9, 30, 0x85, 31, 0x06),
        (32, 0xA9, 34, 0x85, 35, 0x07),
    )
    for a, av, b, bv, c, cv in expected:
        if blob[a] != av or blob[b] != bv or blob[c] != cv:
            raise ValueError("unexpected standard loader encoding")
    if blob[36] != 0x20:
        raise ValueError("standard loader does not end in JSR")

    return ResidentLoader(
        payload_offset=offset,
        lba=blob[21] | (blob[25] << 8),
        byte_length=blob[29] | (blob[33] << 8),
        loader_entry=blob[37] | (blob[38] << 8),
    )


def find_standard_resident_loaders(payload: bytes) -> tuple[ResidentLoader, ...]:
    return tuple(
        _decode_standard_loader(payload, offset)
        for offset in _find_all(payload, STANDARD_RESIDENT_LOADER_PREFIX)
    )


def parse_voice_descriptors(module: bytes) -> tuple[VoiceDescriptor, ...]:
    """Decode the 6-byte command-4 voice descriptor table."""

    relative = VOICE_DESCRIPTOR_CPU - MODULE_CPU_START
    blob = module[relative : relative + VOICE_DESCRIPTOR_BYTES]
    if len(blob) != VOICE_DESCRIPTOR_BYTES:
        raise ValueError("voice descriptor table is truncated")
    if hashlib.sha256(blob).hexdigest() != VOICE_DESCRIPTOR_SHA256:
        raise ValueError("voice descriptor table source guard mismatch")

    rows: list[VoiceDescriptor] = []
    for selector in range(1, VOICE_DESCRIPTOR_COUNT + 1):
        start = (selector - 1) * 6
        entry = blob[start : start + 6]
        lba = (entry[0] << 16) | (entry[2] << 8) | entry[1]
        rows.append(
            VoiceDescriptor(
                selector=selector,
                lba=lba,
                sectors=entry[3],
                parameter_word=entry[4] | (entry[5] << 8),
            )
        )
    return tuple(rows)


def voice_extent_is_contiguous(rows: tuple[VoiceDescriptor, ...]) -> bool:
    return all(
        left.end_lba_exclusive == right.lba
        for left, right in zip(rows, rows[1:])
    )


def immutable_module_sha256(module: bytes) -> str:
    if len(module) != DIALOGUE_MODULE_LENGTH:
        raise ValueError("Mission 0 dialogue module length mismatch")
    filtered = bytearray(module)
    for cpu_address in sorted(MODULE_MUTABLE_CPU_BYTES, reverse=True):
        del filtered[cpu_address - MODULE_CPU_START]
    return hashlib.sha256(filtered).hexdigest()


def validate_self_mod_sites(module: bytes) -> bool:
    if len(module) != DIALOGUE_MODULE_LENGTH:
        return False
    for cpu, opcode, target in SELF_MOD_WRITE_SITES:
        relative = cpu - MODULE_CPU_START
        if module[relative : relative + 3] != bytes(
            (opcode, target & 0xFF, target >> 8)
        ):
            return False
    return True


def analyze_dialogue_residency(payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            f"payload SHA-256 mismatch: expected {TRACK2_PAYLOAD_SHA256}, got {digest}"
        )

    module_offset = payload_offset_for_lba(DIALOGUE_MODULE_LBA)
    module = payload[module_offset : module_offset + DIALOGUE_MODULE_LENGTH]
    loader_start = MISSION0_B_PAYLOAD_BASE + MISSION0_MODULE_LOADER_CPU
    m0_loader = payload[
        loader_start : loader_start + MISSION0_MODULE_LOADER_LENGTH
    ]
    update_relative = MODULE_UPDATE_CPU - MODULE_CPU_START
    outer_start = MISSION0_B_PAYLOAD_BASE + OUTER_EXIT_CPU
    movement_start = MOVEMENT_MODULE_PAYLOAD_BASE + MOVEMENT_EXIT_CPU
    standard_loaders = find_standard_resident_loaders(payload)
    voices = parse_voice_descriptors(module)

    return {
        "module": {
            "lba": "0x%04X" % DIALOGUE_MODULE_LBA,
            "cpu_start": "$8000",
            "cpu_end_inclusive": "$%04X" % (MODULE_CPU_END_EXCLUSIVE - 1),
            "byte_length": DIALOGUE_MODULE_LENGTH,
            "source_sha256_match": hashlib.sha256(module).hexdigest()
            == DIALOGUE_MODULE_SHA256,
            "mutable_source_bytes": [
                "$%04X" % address for address in MODULE_MUTABLE_CPU_BYTES
            ],
            "immutable_sha256": immutable_module_sha256(module),
            "immutable_sha256_match": immutable_module_sha256(module)
            == MODULE_IMMUTABLE_SHA256,
            "self_mod_write_sites": len(SELF_MOD_WRITE_SITES),
            "self_mod_sites_match": validate_self_mod_sites(module),
        },
        "bank_85_layout": {
            "logical_window": "$8000-$9FFF",
            "module": "$8000-$%04X" % (MODULE_CPU_END_EXCLUSIVE - 1),
            "runtime_bss": "$%04X-$8FFF" % MODULE_BSS_START,
            "runtime_bss_bytes": MODULE_BSS_BYTES,
            "speaker_local_block": "$9000-$9FFF",
            "speaker_local_bytes": SPEAKER_LOCAL_BYTES,
            "exact_8k_accounting": (
                DIALOGUE_MODULE_LENGTH + MODULE_BSS_BYTES + SPEAKER_LOCAL_BYTES
                == 0x2000
            ),
            "stock_module_reload_preserves_bss": True,
        },
        "resident_loader": {
            "all_check_hits": len(_find_all(payload, RESIDENT_CHECK)),
            "expected_all_check_hits": EXPECTED_ALL_RESIDENT_CHECKS,
            "standard_loader_copies": len(standard_loaders),
            "expected_standard_loader_copies": EXPECTED_STANDARD_LOADERS,
            "m0_loader_source_guard": hashlib.sha256(m0_loader).hexdigest()
            == MISSION0_MODULE_LOADER_SHA256,
            "check": "LDA $8000; ORA $8003; CMP #$4C",
            "comparison_result_used_by_branch": False,
            "standard_loaders": [
                {
                    "payload_offset": "0x%08X" % item.payload_offset,
                    "lba": "0x%04X" % item.lba,
                    "byte_length": item.byte_length,
                    "sectors_touched": item.sectors_touched,
                    "loader_entry": "$%04X" % item.loader_entry,
                }
                for item in standard_loaders
            ],
        },
        "source_guards": {
            "command_region": hashlib.sha256(
                module[:MODULE_COMMAND_REGION_LENGTH]
            ).hexdigest()
            == MODULE_COMMAND_REGION_SHA256,
            "periodic_update": hashlib.sha256(
                module[
                    update_relative : update_relative + MODULE_UPDATE_LENGTH
                ]
            ).hexdigest()
            == MODULE_UPDATE_SHA256,
            "outer_exit": hashlib.sha256(
                payload[outer_start : outer_start + OUTER_EXIT_LENGTH]
            ).hexdigest()
            == OUTER_EXIT_SHA256,
            "movement_exit": hashlib.sha256(
                payload[movement_start : movement_start + MOVEMENT_EXIT_LENGTH]
            ).hexdigest()
            == MOVEMENT_EXIT_SHA256,
            "movement_fade": payload[
                MOVEMENT_MODULE_PAYLOAD_BASE + MOVEMENT_AUDIO_FADE_CPU :
                MOVEMENT_MODULE_PAYLOAD_BASE
                + MOVEMENT_AUDIO_FADE_CPU
                + len(MOVEMENT_AUDIO_FADE_BYTES)
            ]
            == MOVEMENT_AUDIO_FADE_BYTES,
        },
        "audio_state_machine": {
            "command_0": "reset public audio state and invalidate $8FDE",
            "command_1": (
                "reuse 2-sector local block only when selector==$8FDE; "
                "then always AD_STOP/wait and AD_TRANS the 4-sector block"
            ),
            "command_2": (
                "PSG_FDOUT parameter $1E + CD_FADE $0E; set $37F0=$FF"
            ),
            "command_4": (
                "voice/sample start; descriptor-driven code contains additional "
                "AD_TRANS traffic, so ADPCM RAM cannot be assumed reusable"
            ),
            "command_5": (
                "immediate shutdown; clear $37F0/$37F1/$37F2 and "
                "invalidate $8FDE"
            ),
            "outer_wait": (
                "when $420B is set, wait at $41EC until periodic PSG status "
                "handling clears $37F0"
            ),
        },
        "exploration_audio_transition": {
            "cd_fade_mode": "0x0C",
            "fixed_vsync_frames": 120,
            "fixed_vsync_seconds_at_60hz": 2.0,
            "entry_music_path": (
                "$4089 cancels prior fade then calls CD_PLAY before the "
                "interactive exploration loop"
            ),
        },
        "voice_extent": {
            "descriptor_count": len(voices),
            "descriptor_cpu": "$8BA3",
            "descriptor_sha256": VOICE_DESCRIPTOR_SHA256,
            "first_lba": "0x%04X" % voices[0].lba,
            "end_lba_exclusive": "0x%04X" % voices[-1].end_lba_exclusive,
            "contiguous": voice_extent_is_contiguous(voices),
            "total_sectors": sum(item.sectors for item in voices),
            "total_bytes": sum(item.sectors for item in voices) * 0x800,
            "minimum_1x_seconds": sum(item.sectors for item in voices) / 75.0,
            "largest_clip_sectors": max(item.sectors for item in voices),
            "cache_conclusion": (
                "the full Mission 0 voice corpus is far larger than 192 KiB; "
                "cache/prefetch must operate on the current conversation or "
                "hot voice subset rather than the complete mission"
            ),
        },
        "optimization_hypotheses": [
            (
                "resident module: authenticate immutable bytes, reset "
                "$8617/$8618, and skip the module CD reload"
            ),
            (
                "speaker local block: it occupies the other half of the same "
                "8 KiB bank and may also survive exploration; stock cache "
                "metadata is deliberately invalidated on full teardown"
            ),
            (
                "cache ADPCM source in ordinary/Super CD RAM rather than assume "
                "ADPCM RAM remains unchanged, because command 4 performs "
                "additional descriptor-driven AD_TRANS operations"
            ),
            (
                "shorten CD-DA transition policy only with an explicit safe "
                "audio stop/pause state before the next data seek"
            ),
        ],
        "release_enabled": False,
    }
