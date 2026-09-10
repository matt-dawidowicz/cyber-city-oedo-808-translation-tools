"""Typed, lossless nodes for the game's ``27 28`` dialogue bytecode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class TextRun:
    """Represent one contiguous Shift-JIS text run from a dialogue stream."""

    offset: int
    raw: bytes
    text: str
    character_count: int

    def __post_init__(self) -> None:
        """Verify offset, text, byte identity, and character count."""

        if self.offset < 0:
            raise ValueError("text offset must be non-negative")
        if not self.raw:
            raise ValueError("text run must contain source bytes")
        if not self.text:
            raise ValueError("text run must contain visible text")
        if self.character_count <= 0:
            raise ValueError("character_count must be positive")
        try:
            encoded = self.text.encode("shift_jis")
        except UnicodeEncodeError as error:
            raise ValueError("text run is not Shift-JIS encodable") from error
        if encoded != self.raw:
            raise ValueError("text run bytes do not match its decoded text")

    @property
    def end_offset(self) -> int:
        """Return the exclusive source end offset."""

        return self.offset + len(self.raw)


@dataclass(frozen=True, slots=True)
class ControlCommand:
    """Represent one dialogue command with its exact operand bytes."""

    offset: int
    opcode: int
    operands: bytes
    name: str | None

    def __post_init__(self) -> None:
        """Validate command offset, opcode range, and optional name."""

        if self.offset < 0:
            raise ValueError("control offset must be non-negative")
        if not 0 < self.opcode < 0x80:
            raise ValueError("control opcode must be in the range 01-7F")
        if self.name is not None and not self.name:
            raise ValueError("control name must be non-empty when supplied")

    @property
    def raw(self) -> bytes:
        """Return opcode plus operands exactly as stored in the source."""

        return bytes((self.opcode,)) + self.operands

    @property
    def end_offset(self) -> int:
        """Return the exclusive source end offset."""

        return self.offset + 1 + len(self.operands)

    @property
    def is_known(self) -> bool:
        """Return whether this node came from an established opcode spec."""

        return self.name is not None

    def semantic_tag(self) -> str:
        """Render an audit tag that keeps operands attached to the opcode."""

        if not self.operands:
            return f"<${self.opcode:02X}>"
        operand_text = " ".join(f"{value:02X}" for value in self.operands)
        return f"<${self.opcode:02X}:{operand_text}>"

    def legacy_tags(self) -> tuple[str, ...]:
        """Render raw-byte tags compatible with the version-1 TSV surface."""

        return tuple(f"<${value:02X}>" for value in self.raw)


DialogueNode: TypeAlias = TextRun | ControlCommand


@dataclass(frozen=True, slots=True)
class DialogueBody:
    """Represent a body after ``27 28`` and before its final ``00``."""

    start_offset: int
    terminator_offset: int
    nodes: tuple[DialogueNode, ...]

    def __post_init__(self) -> None:
        """Require nodes to cover every body byte contiguously."""

        if self.start_offset < 0:
            raise ValueError("body start must be non-negative")
        if self.terminator_offset < self.start_offset:
            raise ValueError("terminator cannot precede the body")
        expected = self.start_offset
        for node in self.nodes:
            if node.offset != expected:
                raise ValueError("dialogue nodes must cover source bytes contiguously")
            expected = node.end_offset
        if expected != self.terminator_offset:
            raise ValueError("dialogue nodes must end immediately before terminator")

    @property
    def end_offset(self) -> int:
        """Return the inclusive terminator offset for compatibility."""

        return self.terminator_offset

    @property
    def visible_text(self) -> str:
        """Return concatenated visible text with bytecode commands omitted."""

        return "".join(node.text for node in self.nodes if isinstance(node, TextRun))

    @property
    def sjis_characters(self) -> int:
        """Return the number of decoded Shift-JIS glyphs."""

        return sum(
            node.character_count for node in self.nodes if isinstance(node, TextRun)
        )

    @property
    def commands(self) -> tuple[ControlCommand, ...]:
        """Return control nodes in encounter order."""

        return tuple(node for node in self.nodes if isinstance(node, ControlCommand))

    @property
    def control_opcodes(self) -> tuple[int, ...]:
        """Return command opcodes without their operand bytes."""

        return tuple(command.opcode for command in self.commands)

    @property
    def legacy_control_bytes(self) -> tuple[int, ...]:
        """Flatten command bytes for compatibility with the v1 TSV schema."""

        return tuple(value for command in self.commands for value in command.raw)

    @property
    def tagged_text(self) -> str:
        """Render visible text with operand-aware command tags."""

        return "".join(
            node.text if isinstance(node, TextRun) else node.semantic_tag()
            for node in self.nodes
        )

    @property
    def legacy_tagged_text(self) -> str:
        """Render text with one raw tag per byte for v1 compatibility."""

        parts: list[str] = []
        for node in self.nodes:
            if isinstance(node, TextRun):
                parts.append(node.text)
            else:
                parts.extend(node.legacy_tags())
        return "".join(parts)


@dataclass(frozen=True, slots=True)
class DialogueRecord:
    """Represent one complete marker-through-terminator dialogue record."""

    marker_offset: int
    body: DialogueBody

    def __post_init__(self) -> None:
        """Require the body to begin immediately after the two-byte marker."""

        if self.marker_offset < 0:
            raise ValueError("marker offset must be non-negative")
        if self.body.start_offset != self.marker_offset + 2:
            raise ValueError("body must begin immediately after the two-byte marker")

    @property
    def end_offset(self) -> int:
        """Return the inclusive terminator offset."""

        return self.body.terminator_offset

    @property
    def byte_count(self) -> int:
        """Return marker-through-terminator byte count."""

        return self.end_offset - self.marker_offset + 1


__all__ = [
    "ControlCommand",
    "DialogueBody",
    "DialogueNode",
    "DialogueRecord",
    "TextRun",
]
