#!/usr/bin/env python3
"""Disassemble HuC6280 machine code from a payload or extracted module.

The game mixes executable code, text, graphics, and tables in one directoryless
data track. This utility intentionally performs linear disassembly only: the
caller must supply a known code offset, CPU load address, and byte count. It
does not claim that arbitrary data is executable or attempt to infer the
PC Engine CD memory-page-register state.

The opcode and addressing-mode matrix follows MAME's BSD-3-Clause HuC6280
disassembler by Bryan McPhail. The Python implementation and output format are
project-specific and keep payload offsets beside CPU addresses so findings can
be reproduced against the authenticated disc image.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass
from typing import Iterable, Sequence


# Each row describes opcodes whose high nibble is the row index. Keeping the
# matrix visible makes incorrect instruction boundaries easier to audit.
_OPCODE_ROWS = (
    "brk:imp ora:idx sxy:imp st0:imm tsb:zpg ora:zpg asl:zpg "
    "rmb0:zpg php:imp ora:imm asl:acc ill:non tsb:abs ora:abs "
    "asl:abs bbr0:zrl",
    "bpl:rel ora:idy ora:zpi st1:imm trb:zpg ora:zpx asl:zpx "
    "rmb1:zpg clc:imp ora:aby ina:imp ill:non trb:abs ora:abx "
    "asl:abx bbr1:zrl",
    "jsr:abs and:idx sax:imp st2:imm bit:zpg and:zpg rol:zpg "
    "rmb2:zpg plp:imp and:imm rol:acc ill:non bit:abs and:abs "
    "rol:abs bbr2:zrl",
    "bmi:rel and:idy and:zpi ill:non bit:zpx and:zpx rol:zpx "
    "rmb3:zpg sec:imp and:aby dea:imp ill:non bit:abx and:abx "
    "rol:abx bbr3:zrl",
    "rti:imp eor:idx say:imp tma:imm bsr:rel eor:zpg lsr:zpg "
    "rmb4:zpg pha:imp eor:imm lsr:acc ill:non jmp:abs eor:abs "
    "lsr:abs bbr4:zrl",
    "bvc:rel eor:idy eor:zpi tam:imm csl:imp eor:zpx lsr:zpx "
    "rmb5:zpg cli:imp eor:aby phy:imp ill:non ill:non eor:abx "
    "lsr:abx bbr5:zrl",
    "rts:imp adc:idx cla:imp ill:non stz:zpg adc:zpg ror:zpg "
    "rmb6:zpg pla:imp adc:imm ror:acc ill:non jmp:ind adc:abs "
    "ror:abs bbr6:zrl",
    "bvs:rel adc:idy adc:zpi tii:blk stz:zpx adc:zpx ror:zpx "
    "rmb7:zpg sei:imp adc:aby ply:imp ill:non jmp:iax adc:abx "
    "ror:abx bbr7:zrl",
    "bra:rel sta:idx clx:imp tst:imz sty:zpg sta:zpg stx:zpg "
    "smb0:zpg dey:imp bit:imm txa:imp ill:non sty:abs sta:abs "
    "stx:abs bbs0:zrl",
    "bcc:rel sta:idy sta:zpi tst:ima sty:zpx sta:zpx stx:zpy "
    "smb1:zpg tya:imp sta:aby txs:imp ill:non stz:abs sta:abx "
    "stz:abx bbs1:zrl",
    "ldy:imm lda:idx ldx:imm tst:izx ldy:zpg lda:zpg ldx:zpg "
    "smb2:zpg tay:imp lda:imm tax:imp ill:non ldy:abs lda:abs "
    "ldx:abs bbs2:zrl",
    "bcs:rel lda:idy lda:zpi tst:imx ldy:zpx lda:zpx ldx:zpy "
    "smb3:zpg clv:imp lda:aby tsx:imp ill:non ldy:abx lda:abx "
    "ldx:aby bbs3:zrl",
    "cpy:imm cmp:idx cly:imp tdd:blk cpy:zpg cmp:zpg dec:zpg "
    "smb4:zpg iny:imp cmp:imm dex:imp ill:non cpy:abs cmp:abs "
    "dec:abs bbs4:zrl",
    "bne:rel cmp:idy cmp:zpi tin:blk csh:imp cmp:zpx dec:zpx "
    "smb5:zpg cld:imp cmp:aby phx:imp ill:non ill:non cmp:abx "
    "dec:abx bbs5:zrl",
    "cpx:imm sbc:idx ill:non tia:blk cpx:zpg sbc:zpg inc:zpg "
    "smb6:zpg inx:imp sbc:imm nop:imp ill:non cpx:abs sbc:abs "
    "inc:abs bbs6:zrl",
    "beq:rel sbc:idy sbc:zpi tai:blk set:imp sbc:zpx inc:zpx "
    "smb7:zpg sed:imp sbc:aby plx:imp ill:non ill:non sbc:abx "
    "inc:abx bbs7:zrl",
)

_MODE_LENGTHS = {
    "non": 1,
    "acc": 1,
    "imp": 1,
    "imm": 2,
    "zpg": 2,
    "zpx": 2,
    "zpy": 2,
    "zpi": 2,
    "rel": 2,
    "idx": 2,
    "idy": 2,
    "abs": 3,
    "abx": 3,
    "aby": 3,
    "ind": 3,
    "iax": 3,
    "zrl": 3,
    "imz": 3,
    "izx": 3,
    "ima": 4,
    "imx": 4,
    "blk": 7,
}


def _build_opcode_table() -> tuple[tuple[str, str], ...]:
    """Build and validate the complete 256-entry opcode table.

    Returns:
        Tuples containing the lowercase mnemonic and addressing-mode name for
        opcodes `0x00` through `0xFF`.

    Raises:
        RuntimeError: If a row has the wrong number of entries or references
            an addressing mode without a known instruction length.
    """

    table: list[tuple[str, str]] = []
    for row_number, row in enumerate(_OPCODE_ROWS):
        entries = row.split()
        if len(entries) != 16:
            raise RuntimeError(f"opcode row {row_number:X} has {len(entries)} entries")
        for entry in entries:
            mnemonic, mode = entry.split(":", maxsplit=1)
            if mode not in _MODE_LENGTHS:
                raise RuntimeError(f"unknown addressing mode: {mode}")
            table.append((mnemonic, mode))
    if len(table) != 256:
        raise RuntimeError(f"opcode table has {len(table)} entries")
    return tuple(table)


OPCODES = _build_opcode_table()


@dataclass(frozen=True, slots=True)
class Instruction:
    """Represent one decoded HuC6280 instruction.

    Attributes:
        payload_offset: File offset of the opcode in the supplied binary.
        cpu_address: Logical 16-bit address assigned by the caller.
        raw: Complete instruction bytes.
        mnemonic: Lowercase HuC6280 instruction name.
        operand: Formatted operand text, or an empty string.
    """

    payload_offset: int
    cpu_address: int
    raw: bytes
    mnemonic: str
    operand: str

    def format(self) -> str:
        """Return one stable, address-rich disassembly line.

        Returns:
            A line containing payload offset, CPU address, raw bytes,
            mnemonic, and formatted operand.
        """

        raw_text = self.raw.hex(" ").upper()
        operation = f"{self.mnemonic.upper():<5} {self.operand}".rstrip()
        return (
            f"{self.payload_offset:08X}  "
            f"{self.cpu_address:04X}  "
            f"{raw_text:<20}  "
            f"{operation}"
        )


def _signed_byte(value: int) -> int:
    """Interpret an unsigned byte as a signed branch displacement.

    Args:
        value: Integer in the inclusive range `0x00` through `0xFF`.

    Returns:
        The equivalent integer in the range -128 through 127.
    """

    return value - 0x100 if value & 0x80 else value


def _word(data: bytes, index: int) -> int:
    """Read one little-endian 16-bit value.

    Args:
        data: Complete instruction bytes.
        index: Index of the low byte.

    Returns:
        The decoded unsigned word.
    """

    return data[index] | (data[index + 1] << 8)


def _format_operand(mode: str, raw: bytes, cpu_address: int) -> str:
    """Format an operand using conventional HuC6280 syntax.

    Args:
        mode: Addressing-mode name from `OPCODES`.
        raw: Complete instruction bytes.
        cpu_address: Logical address of the opcode.

    Returns:
        A formatted operand, or an empty string for implicit instructions.
    """

    if mode in {"non", "imp"}:
        return ""
    if mode == "acc":
        return "A"
    if mode == "imm":
        return f"#$%02X" % raw[1]
    if mode == "zpg":
        return f"$%02X" % raw[1]
    if mode == "zpx":
        return f"$%02X,X" % raw[1]
    if mode == "zpy":
        return f"$%02X,Y" % raw[1]
    if mode == "zpi":
        return f"($%02X)" % raw[1]
    if mode == "idx":
        return f"($%02X,X)" % raw[1]
    if mode == "idy":
        return f"($%02X),Y" % raw[1]
    if mode == "abs":
        return f"$%04X" % _word(raw, 1)
    if mode == "abx":
        return f"$%04X,X" % _word(raw, 1)
    if mode == "aby":
        return f"$%04X,Y" % _word(raw, 1)
    if mode == "ind":
        return f"($%04X)" % _word(raw, 1)
    if mode == "iax":
        return f"($%04X,X)" % _word(raw, 1)
    if mode == "rel":
        target = (cpu_address + 2 + _signed_byte(raw[1])) & 0xFFFF
        return f"$%04X" % target
    if mode == "zrl":
        target = (cpu_address + 3 + _signed_byte(raw[2])) & 0xFFFF
        return f"$%02X,$%04X" % (raw[1], target)
    if mode == "imz":
        return f"#$%02X,$%02X" % (raw[1], raw[2])
    if mode == "izx":
        return f"#$%02X,$%02X,X" % (raw[1], raw[2])
    if mode == "ima":
        return f"#$%02X,$%04X" % (raw[1], _word(raw, 2))
    if mode == "imx":
        return f"#$%02X,$%04X,X" % (raw[1], _word(raw, 2))
    if mode == "blk":
        return "$%04X,$%04X,$%04X" % (
            _word(raw, 1),
            _word(raw, 3),
            _word(raw, 5),
        )
    raise ValueError(f"unsupported addressing mode: {mode}")


def decode_instruction(
    data: bytes,
    index: int,
    payload_offset: int,
    cpu_address: int,
) -> Instruction:
    """Decode one instruction without reading beyond the supplied data.

    Args:
        data: Binary region containing the opcode and operands.
        index: Byte index of the opcode inside `data`.
        payload_offset: File offset corresponding to `data[index]`.
        cpu_address: Logical CPU address corresponding to `data[index]`.

    Returns:
        The decoded instruction.

    Raises:
        ValueError: If `index` is outside `data` or the instruction is
            truncated.
    """

    if not 0 <= index < len(data):
        raise ValueError("instruction index is outside the data")
    opcode = data[index]
    mnemonic, mode = OPCODES[opcode]
    length = _MODE_LENGTHS[mode]
    raw = data[index : index + length]
    if len(raw) != length:
        raise ValueError(
            f"truncated instruction at payload offset 0x{payload_offset:08X}"
        )
    return Instruction(
        payload_offset=payload_offset,
        cpu_address=cpu_address & 0xFFFF,
        raw=raw,
        mnemonic=mnemonic,
        operand=_format_operand(mode, raw, cpu_address),
    )


def linear_disassemble(
    data: bytes,
    payload_offset: int,
    cpu_address: int,
) -> Iterable[Instruction]:
    """Yield a linear disassembly of one caller-confirmed code region.

    Args:
        data: Exact bytes in the requested region.
        payload_offset: Payload or file offset of `data[0]`.
        cpu_address: Logical address assigned to `data[0]`.

    Yields:
        Decoded instructions until the region is exhausted.

    Raises:
        ValueError: If the final instruction is truncated.

    Design Decisions:
        The function does not stop at returns, jumps, or data-looking bytes.
        This makes it deterministic and keeps code/data decisions with the
        analyst who has the relevant load and control-flow evidence.
    """

    index = 0
    while index < len(data):
        instruction = decode_instruction(
            data,
            index,
            payload_offset + index,
            cpu_address + index,
        )
        yield instruction
        index += len(instruction.raw)


def read_binary_region(
    path: pathlib.Path,
    offset: int,
    length: int,
) -> bytes:
    """Read exactly one bounded binary region from disk.

    Args:
        path: Binary file to inspect.
        offset: Non-negative byte offset.
        length: Positive number of bytes to return.

    Returns:
        Exactly ``length`` bytes beginning at ``offset``.

    Raises:
        ValueError: If coordinates are invalid, exceed the open file, or a
            short read occurs.
        OSError: If opening, seeking, or reading the file fails.
    """

    if offset < 0:
        raise ValueError("offset must be non-negative")
    if length <= 0:
        raise ValueError("length must be positive")
    with path.open("rb") as source:
        file_size = source.seek(0, 2)
        end = offset + length
        if end > file_size:
            raise ValueError(
                f"requested region ends at 0x{end:X}; file size is 0x{file_size:X}"
            )
        source.seek(offset)
        region = source.read(length)
    if len(region) != length:
        raise ValueError(f"short read: expected {length} bytes, found {len(region)}")
    return region


def parse_int(value: str) -> int:
    """Parse a decimal integer or a hexadecimal value prefixed by `0x`.

    Args:
        value: Command-line integer spelling.

    Returns:
        The parsed non-negative integer.

    Raises:
        argparse.ArgumentTypeError: If parsing fails or the value is negative.
    """

    try:
        parsed = int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must not be negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser.

    Returns:
        Parser requiring a binary path, file offset, CPU address, and length.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Linearly disassemble a confirmed HuC6280 code region while "
            "showing both file offsets and logical CPU addresses."
        )
    )
    parser.add_argument("binary", type=pathlib.Path)
    parser.add_argument(
        "--offset",
        required=True,
        type=parse_int,
        help="file or payload byte offset, decimal or 0x-prefixed",
    )
    parser.add_argument(
        "--address",
        required=True,
        type=parse_int,
        help="logical CPU address corresponding to --offset",
    )
    parser.add_argument(
        "--length",
        required=True,
        type=parse_int,
        help="number of bytes to decode",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the linear disassembler.

    Args:
        argv: Optional arguments without the program name.

    Returns:
        Zero after every requested byte is decoded and printed.

    Side Effects:
        Reads the supplied binary and writes disassembly to standard output.

    Failure Conditions:
        File errors, out-of-range regions, and truncated final instructions
        terminate the command with an exception instead of producing a
        misleading partial result.
    """

    args = build_parser().parse_args(argv)
    region = read_binary_region(
        args.binary,
        args.offset,
        args.length,
    )
    for instruction in linear_disassemble(
        region,
        args.offset,
        args.address,
    ):
        print(instruction.format())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
