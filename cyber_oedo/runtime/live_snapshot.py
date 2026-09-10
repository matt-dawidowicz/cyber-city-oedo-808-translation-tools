"""Validate one frozen Mednafen snapshot of the Mission 0 ``3D`` path.

This module is deliberately read-only.  It turns live debugger state into a
machine-checkable Tier-B artifact without treating a logical CPU address as
sufficient evidence in the HuC6280's bank-switched address space.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_buffer
from cyber_oedo.runtime.dialogue_interpreter import (
    INDEXED_ALTERNATE_TEXT_OFFSET,
    INDEXED_STATE_OFFSET,
    INDEXED_TEXT_SLOT_BYTES,
    indexed_record_address,
    indexed_text_field_offset,
)

CPU_ADDRESS_SPACE = 0x10000
MPR_COUNT = 8
MPR_WINDOW_BYTES = 0x2000
DIRECT_PAGE_CPU_BASE = 0x2000
STREAM_POINTER_ZP = 0x7F
THREE_D_SUCCESS_CPU = 0x9593
MISSION0_INTERPRETER_MPR_SLOT = THREE_D_SUCCESS_CPU // MPR_WINDOW_BYTES
MISSION0_INTERPRETER_MPR = 0x82
THREE_D_OPCODE = 0x3D


def _byte(value: int, name: str) -> int:
    """Validate and return one byte-sized integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must fit in one byte")
    return value


def _word(value: int, name: str) -> int:
    """Validate and return one 16-bit integer."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"{name} must fit in 16 bits")
    return value


def _parse_number(value: Any, name: str) -> int:
    """Parse an integer or base-prefixed numeric string."""
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer or numeric string")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{name} is empty")
        return int(text, 0)
    raise TypeError(f"{name} must be an integer or numeric string")


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    """Freeze logical CPU memory plus registers needed for a ``3D`` proof."""

    pc: int
    a: int
    mprs: tuple[int, ...]
    memory: bytes

    def __post_init__(self) -> None:
        """Validate frozen register and memory dimensions."""
        _word(self.pc, "pc")
        _byte(self.a, "a")
        if len(self.mprs) != MPR_COUNT:
            raise ValueError("exactly eight MPR values are required")
        for index, value in enumerate(self.mprs):
            _byte(value, f"mpr[{index}]")
        if not isinstance(self.memory, bytes):
            raise TypeError("memory must be bytes")
        if len(self.memory) != CPU_ADDRESS_SPACE:
            raise ValueError("logical CPU memory dump must be exactly 65536 bytes")


def logical_to_physical(
    cpu_address: int,
    mprs: tuple[int, ...],
) -> tuple[int, int]:
    """Map a HuC6280 logical address to ``(MPR page, 8 KiB offset)``."""

    address = _word(cpu_address, "cpu address")
    if len(mprs) != MPR_COUNT:
        raise ValueError("exactly eight MPR values are required")
    slot = address // MPR_WINDOW_BYTES
    page = _byte(mprs[slot], f"mpr[{slot}]")
    return page, address & (MPR_WINDOW_BYTES - 1)


def format_physical(cpu_address: int, mprs: tuple[int, ...]) -> str:
    """Return Mednafen-style physical notation for one logical address."""

    page, offset = logical_to_physical(cpu_address, mprs)
    return f"*{page:02X}:{offset:04X}"


def stream_pointer_from_memory(memory: bytes) -> int:
    """Read direct-page ``$7F/$80`` from logical ``$207F/$2080``."""

    if len(memory) != CPU_ADDRESS_SPACE:
        raise ValueError("logical CPU memory dump must be exactly 65536 bytes")
    low_address = DIRECT_PAGE_CPU_BASE + STREAM_POINTER_ZP
    return memory[low_address] | (memory[low_address + 1] << 8)


def _decode_slot(memory: bytes, address: int) -> str:
    """Decode one null-terminated 13-byte Shift-JIS record slot from an indexed record."""
    data = bytes(
        memory[(address + offset) & 0xFFFF] for offset in range(INDEXED_TEXT_SLOT_BYTES)
    )
    terminator = data.find(b"\x00")
    if terminator < 0:
        raise ValueError(f"indexed text slot at ${address:04X} is not null-terminated")
    return data[:terminator].decode("shift_jis")


def prove_three_d_snapshot(snapshot: LiveSnapshot) -> dict[str, Any]:
    """Prove and decode a breakpoint stop at the ``3D`` success path."""

    if snapshot.pc != THREE_D_SUCCESS_CPU:
        raise ValueError(
            f"expected PC ${THREE_D_SUCCESS_CPU:04X}; got ${snapshot.pc:04X}"
        )
    if snapshot.a != THREE_D_OPCODE:
        raise ValueError(
            f"expected A=${THREE_D_OPCODE:02X} after CMP #$3D; got ${snapshot.a:02X}"
        )
    active_page = snapshot.mprs[MISSION0_INTERPRETER_MPR_SLOT]
    if active_page != MISSION0_INTERPRETER_MPR:
        raise ValueError(
            "logical $9593 is not the proven Mission 0 interpreter: "
            f"MPR{MISSION0_INTERPRETER_MPR_SLOT}=${active_page:02X}, "
            f"expected ${MISSION0_INTERPRETER_MPR:02X}"
        )

    stream_pointer = stream_pointer_from_memory(snapshot.memory)
    arg0 = snapshot.memory[stream_pointer]
    arg1 = snapshot.memory[(stream_pointer + 1) & 0xFFFF]
    record_address = indexed_record_address(arg1)
    state_address = (record_address + INDEXED_STATE_OFFSET) & 0xFFFF
    state_byte = snapshot.memory[state_address]
    selected_offset = indexed_text_field_offset(state_byte)
    selected_address = (record_address + selected_offset) & 0xFFFF

    primary_text = _decode_slot(snapshot.memory, record_address)
    alternate_address = (record_address + INDEXED_ALTERNATE_TEXT_OFFSET) & 0xFFFF
    alternate_text = _decode_slot(snapshot.memory, alternate_address)
    selected_text = primary_text if selected_offset == 0 else alternate_text

    return {
        "proof": "mission0-3d-live-snapshot",
        "validated": True,
        "memory_sha256": sha256_buffer(snapshot.memory),
        "pc": f"0x{snapshot.pc:04X}",
        "a": f"0x{snapshot.a:02X}",
        "pc_physical": format_physical(snapshot.pc, snapshot.mprs),
        "mprs": [f"0x{value:02X}" for value in snapshot.mprs],
        "interpreter_mpr_slot": MISSION0_INTERPRETER_MPR_SLOT,
        "interpreter_mpr": f"0x{active_page:02X}",
        "stream_pointer": f"0x{stream_pointer:04X}",
        "stream_pointer_physical": format_physical(
            stream_pointer,
            snapshot.mprs,
        ),
        "operands": {
            "arg0": f"0x{arg0:02X}",
            "arg1": f"0x{arg1:02X}",
            "arg0_semantics": ("read-and-discarded by the proven Mission 0 handler"),
            "arg1_semantics": "one-based 32-byte indexed-record selector",
        },
        "record": {
            "address": f"0x{record_address:04X}",
            "address_physical": format_physical(record_address, snapshot.mprs),
            "state_address": f"0x{state_address:04X}",
            "state_byte": f"0x{state_byte:02X}",
            "primary_text": primary_text,
            "alternate_text": alternate_text,
            "selected_offset": f"0x{selected_offset:02X}",
            "selected_address": f"0x{selected_address:04X}",
            "selected_text": selected_text,
        },
    }


def load_snapshot(
    metadata_path: pathlib.Path,
    memory_path: pathlib.Path,
) -> LiveSnapshot:
    """Load one JSON register/MPR description and 64 KiB logical dump."""

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw_mprs = metadata.get("mprs", metadata.get("mpr"))
    if not isinstance(raw_mprs, list):
        raise ValueError("snapshot metadata must contain an mprs array")
    mprs = tuple(
        _parse_number(value, f"mprs[{index}]") for index, value in enumerate(raw_mprs)
    )
    return LiveSnapshot(
        pc=_parse_number(metadata["pc"], "pc"),
        a=_parse_number(metadata["a"], "a"),
        mprs=mprs,
        memory=memory_path.read_bytes(),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the frozen live-snapshot command-line parser."""

    parser = argparse.ArgumentParser(
        description="Validate one frozen Mission 0 live 3D debugger snapshot."
    )
    parser.add_argument("metadata", type=pathlib.Path)
    parser.add_argument("memory", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate one snapshot and write deterministic JSON evidence."""

    args = build_parser().parse_args(argv)
    report = prove_three_d_snapshot(load_snapshot(args.metadata, args.memory))
    rendered = (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
