"""Static verifier for proposed banked $7B English dialogue redirects.

This module does NOT install a game runtime handler. It verifies the stream
contract that any future HuC6280 loader/dispatcher must obey, including
redirect width, Card-RAM bank ownership, native-English framing, and terminal
control consumption. The experimental image's source has not been recovered.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.script.opcodes import opcode_spec
from cyber_oedo.text.english_dialogue_engine import (
    ENGLISH_GLYPH_BASE,
    ENGLISH_GLYPH_LAST,
    ENGLISH_MODE_SIGNATURE,
    ENGLISH_SEGMENT_END,
)
from cyber_oedo.text.vwf_cells import (
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VWF_TOKEN_FIRST_MAX,
    VWF_TOKEN_FIRST_MIN,
)

POOL_REDIRECT_PREFIX = bytes.fromhex("27 28 7B")
POOL_FIRST_BANK = 0x7C
POOL_LAST_BANK = 0x7F
POOL_BANK_BYTES = 0x2000
POOL_CPU_WINDOW = 0x6000
POOL_CAPACITY = (POOL_LAST_BANK - POOL_FIRST_BANK + 1) * POOL_BANK_BYTES
POOL_REDIRECT_BYTES = 6  # 27 28 7B offset_lo offset_hi 00 (provisional)
POOL_DEFAULT_SCAN_LIMIT = 4096


class ExternalPoolContractError(ValueError):
    """Raised when a candidate pool cannot be handled without ambiguity."""


@dataclass(frozen=True, slots=True)
class PoolAddress:
    absolute_offset: int
    bank: int
    cpu_address: int


@dataclass(frozen=True, slots=True)
class PoolRecordAudit:
    start_offset: int
    end_offset_exclusive: int
    consumed_bytes: int
    bank_range: tuple[int, ...]
    fixed_segments: int
    vwf_segments: int
    stock_controls: tuple[int, ...]


def pool_address(offset: int) -> PoolAddress:
    """Map a linear mission-pool byte index into MPR3's 8 KiB window."""
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise ExternalPoolContractError("pool offset must be an integer")
    if not 0 <= offset < POOL_CAPACITY:
        raise ExternalPoolContractError("pool offset lies outside four Card-RAM banks")
    return PoolAddress(
        absolute_offset=offset,
        bank=POOL_FIRST_BANK + offset // POOL_BANK_BYTES,
        cpu_address=POOL_CPU_WINDOW + offset % POOL_BANK_BYTES,
    )


def decode_pool_redirect(record: bytes) -> int:
    """Validate the provisional six-byte redirect and return its pool offset.

    The exact source redirect footprint still requires authenticated-image
    evidence. A differently shaped redirect must NOT be guessed or emitted.
    """
    if len(record) != POOL_REDIRECT_BYTES or not record.startswith(
        POOL_REDIRECT_PREFIX
    ) or record[-1] != 0:
        raise ExternalPoolContractError(
            "redirect must be 27 28 7B followed by u16 LE offset and 00"
        )
    offset = int.from_bytes(record[3:5], "little")
    pool_address(offset)
    return offset


def inspect_native_pool_record(
    pool: bytes,
    start_offset: int,
    *,
    max_bytes: int = POOL_DEFAULT_SCAN_LIMIT,
) -> PoolRecordAudit:
    """Parse one self-terminated English record across mapped pool pages.

    Native $7D $45/$56 segments are parsed differently from stock low-byte
    commands. Zero valued operands to $2A/$3D/$7E must not terminate the
    record. The verifier refuses unknown controls and bytes that require
    guessing Japanese fallback semantics.
    """
    if len(pool) != POOL_CAPACITY:
        raise ExternalPoolContractError(
            f"pool must be exactly {POOL_CAPACITY} bytes (banks $7C-$7F)"
        )
    if not 1 <= max_bytes <= POOL_CAPACITY:
        raise ExternalPoolContractError("invalid scan limit")
    pool_address(start_offset)
    cursor = start_offset
    deadline = min(POOL_CAPACITY, start_offset + max_bytes)
    fixed_segments = 0
    vwf_segments = 0
    stock_controls: list[int] = []
    seen_native = False

    def require(count: int) -> None:
        if cursor + count > deadline:
            raise ExternalPoolContractError("pool record is truncated or unterminated")

    while cursor < deadline:
        byte = pool[cursor]
        if byte == 0:
            if not seen_native:
                raise ExternalPoolContractError("pool record has no native text")
            end = cursor + 1
            first_bank = pool_address(start_offset).bank
            last_bank = pool_address(cursor).bank
            return PoolRecordAudit(
                start_offset,
                end,
                end - start_offset,
                tuple(range(first_bank, last_bank + 1)),
                fixed_segments,
                vwf_segments,
                tuple(stock_controls),
            )

        if byte == 0x7D:
            require(2)
            signature = pool[cursor : cursor + 2]
            if signature == ENGLISH_MODE_SIGNATURE:
                fixed_segments += 1
                cursor += 2
                had_glyph = False
                while True:
                    require(1)
                    value = pool[cursor]
                    cursor += 1
                    if value == ENGLISH_SEGMENT_END:
                        if not had_glyph:
                            raise ExternalPoolContractError("empty fixed-English segment")
                        break
                    if not ENGLISH_GLYPH_BASE <= value <= ENGLISH_GLYPH_LAST:
                        raise ExternalPoolContractError(
                            f"invalid fixed-English glyph 0x{value:02X}"
                        )
                    had_glyph = True
                seen_native = True
                continue
            if signature == VWF_MODE_SIGNATURE:
                vwf_segments += 1
                cursor += 2
                had_cell = False
                while True:
                    require(2)
                    high, low = pool[cursor], pool[cursor + 1]
                    cursor += 2
                    if high == (VWF_SEGMENT_END_TOKEN >> 8):
                        if low != (VWF_SEGMENT_END_TOKEN & 0xFF) or not had_cell:
                            raise ExternalPoolContractError("invalid VWF segment terminator")
                        break
                    if not VWF_TOKEN_FIRST_MIN <= high <= VWF_TOKEN_FIRST_MAX:
                        raise ExternalPoolContractError("invalid VWF Card-RAM bank token")
                    had_cell = True
                seen_native = True
                continue
            raise ExternalPoolContractError("unknown native signature after $7D")

        spec = opcode_spec(byte)
        if spec is None:
            raise ExternalPoolContractError(
                f"unknown byte 0x{byte:02X} outside English segments"
            )
        require(1 + spec.operand_bytes)
        stock_controls.append(byte)
        cursor += 1 + spec.operand_bytes

    raise ExternalPoolContractError("pool record has no terminator within owned banks")


__all__ = [
    "POOL_BANK_BYTES",
    "POOL_CAPACITY",
    "POOL_FIRST_BANK",
    "POOL_LAST_BANK",
    "POOL_REDIRECT_PREFIX",
    "ExternalPoolContractError",
    "PoolAddress",
    "PoolRecordAudit",
    "decode_pool_redirect",
    "inspect_native_pool_record",
    "pool_address",
]
