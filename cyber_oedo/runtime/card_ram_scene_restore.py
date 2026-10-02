"""HuC6280 code generation for the bar Card-RAM scene restore candidate.

The restore direction (Card RAM -> VDC) reuses the same TIA/VDC mechanism that
was live-validated by the portrait cache benchmark.  The inverse VDC -> Card RAM
snapshot uses the natural TAI form but remains a candidate until the VDC read
latch/dummy-read behavior is verified live.
"""

from __future__ import annotations

from dataclasses import dataclass

CARD_RAM_BANK_BYTES = 0x2000

# Live-diff-authoritative bar spans.
SCENE_SPANS = (
    (0x1200, 0x8E20),  # VRAM byte start, byte length
    (0xDA00, 0x1A00),
)
SCENE_BANK_FIRST = 0x6D


@dataclass(frozen=True, slots=True)
class TransferChunk:
    bank: int
    vram_byte_start: int
    byte_length: int

    @property
    def vram_word_start(self) -> int:
        if self.vram_byte_start & 1:
            raise ValueError("VDC word destination must be even-byte aligned")
        return self.vram_byte_start // 2


def build_scene_chunks() -> tuple[TransferChunk, ...]:
    chunks: list[TransferChunk] = []
    bank = SCENE_BANK_FIRST
    for start, length in SCENE_SPANS:
        cursor = start
        remaining = length
        while remaining:
            amount = min(remaining, CARD_RAM_BANK_BYTES)
            chunks.append(TransferChunk(bank, cursor, amount))
            bank += 1
            cursor += amount
            remaining -= amount
    return tuple(chunks)


def _restore_one_chunk(chunk: TransferChunk) -> bytes:
    """Emit a self-contained Card-RAM -> VDC TIA routine for one bank."""

    word = chunk.vram_word_start
    length = chunk.byte_length
    if length <= 0 or length > 0xFFFF:
        raise ValueError("invalid transfer length")
    return bytes(
        (
            0x43, 0x01,             # TMA #$01 - save MPR0 in A
            0x48,                   # PHA
            0x43, 0x20,             # TMA #$20 - save MPR5
            0x48,                   # PHA
            0xA9, 0xFF,             # LDA #$FF
            0x53, 0x01,             # TAM #$01 - map I/O into MPR0
            0xA9, chunk.bank,
            0x53, 0x20,             # TAM #$20 - Card RAM at $A000
            0x03, 0x00,             # ST0 #$00 - MAWR
            0x13, word & 0xFF,      # ST1 low
            0x23, (word >> 8) & 0xFF,  # ST2 high
            0x03, 0x02,             # ST0 #$02 - VWR
            0xE3, 0x00, 0xA0, 0x02, 0x00, length & 0xFF, (length >> 8) & 0xFF,
            0x68,                   # PLA old MPR5
            0x53, 0x20,
            0x68,                   # PLA old MPR0
            0x53, 0x01,
            0x60,                   # RTS
        )
    )


def build_restore_routines() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "bank": f"$%02X" % chunk.bank,
            "vram_byte_start": f"$%04X" % chunk.vram_byte_start,
            "vram_word_start": f"$%04X" % chunk.vram_word_start,
            "byte_length": chunk.byte_length,
            "machine_code": _restore_one_chunk(chunk),
            "direction_live_proven": True,
        }
        for chunk in build_scene_chunks()
    )


def build_snapshot_plan() -> dict[str, object]:
    return {
        "chunks": [
            {
                "bank": f"$%02X" % chunk.bank,
                "vram_byte_start": f"$%04X" % chunk.vram_byte_start,
                "vram_word_start": f"$%04X" % chunk.vram_word_start,
                "byte_length": chunk.byte_length,
                "candidate_transfer": "TAI $0002,$A000,length after MARR/VRR setup",
            }
            for chunk in build_scene_chunks()
        ],
        "required_validation": [
            "confirm VDC register-2 read-port behavior for block transfer",
            "determine whether a dummy VRR read is required after setting MARR",
            "compare all 43,040 captured bytes against a direct pre-dialogue VRAM dump",
        ],
        "release_enabled": False,
    }
