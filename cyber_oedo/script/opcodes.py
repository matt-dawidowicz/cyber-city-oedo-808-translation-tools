"""Dialogue bytecode constants established from the active game parser."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from cyber_oedo.disc.game_layout import DIALOGUE_MARKER

DIALOGUE_TERMINATOR = 0x00
DEFAULT_PARSE_LIMIT = 1024


class DialogueOpcode(IntEnum):
    """Name known low-byte commands in the ``27 28`` dialogue interpreter."""

    WAIT_STATE = 0x21
    COMMAND_2A = 0x2A
    TIMED_WAIT = 0x2F
    INDIRECT_TEXT = 0x3D
    PAGE_BREAK = 0x40
    WAIT_INPUT = 0x5C
    COMMAND_7E = 0x7E


@dataclass(frozen=True, slots=True)
class OpcodeSpec:
    """Describe one statically established dialogue command shape."""

    opcode: DialogueOpcode
    operand_bytes: int
    name: str

    def __post_init__(self) -> None:
        """Validate the fixed command-shape metadata."""

        if self.operand_bytes < 0:
            raise ValueError("operand_bytes must be non-negative")
        if not self.name:
            raise ValueError("opcode name must not be empty")


OPCODE_SPECS: dict[int, OpcodeSpec] = {
    int(DialogueOpcode.WAIT_STATE): OpcodeSpec(
        DialogueOpcode.WAIT_STATE,
        0,
        "wait_state",
    ),
    int(DialogueOpcode.COMMAND_2A): OpcodeSpec(
        DialogueOpcode.COMMAND_2A,
        1,
        "command_2a",
    ),
    int(DialogueOpcode.TIMED_WAIT): OpcodeSpec(
        DialogueOpcode.TIMED_WAIT,
        0,
        "timed_wait",
    ),
    int(DialogueOpcode.INDIRECT_TEXT): OpcodeSpec(
        DialogueOpcode.INDIRECT_TEXT,
        2,
        "indirect_text",
    ),
    int(DialogueOpcode.PAGE_BREAK): OpcodeSpec(
        DialogueOpcode.PAGE_BREAK,
        0,
        "page_break",
    ),
    int(DialogueOpcode.WAIT_INPUT): OpcodeSpec(
        DialogueOpcode.WAIT_INPUT,
        0,
        "wait_input",
    ),
    int(DialogueOpcode.COMMAND_7E): OpcodeSpec(
        DialogueOpcode.COMMAND_7E,
        1,
        "command_7e",
    ),
}


def opcode_spec(value: int) -> OpcodeSpec | None:
    """Return the known command shape for *value*, if one is established."""

    return OPCODE_SPECS.get(value)


__all__ = [
    "DEFAULT_PARSE_LIMIT",
    "DIALOGUE_MARKER",
    "DIALOGUE_TERMINATOR",
    "DialogueOpcode",
    "OpcodeSpec",
    "OPCODE_SPECS",
    "opcode_spec",
]
