"""Serialize parsed dialogue bytecode without losing source information."""

from __future__ import annotations

from .ast import ControlCommand, DialogueBody, DialogueRecord, TextRun
from .opcodes import DIALOGUE_MARKER, DIALOGUE_TERMINATOR


def serialize_dialogue_body(body: DialogueBody) -> bytes:
    """Serialize a parsed body through exact node bytes plus terminator."""

    output = bytearray()
    for node in body.nodes:
        if isinstance(node, TextRun):
            output.extend(node.raw)
        elif isinstance(node, ControlCommand):
            output.extend(node.raw)
        else:  # pragma: no cover - defensive against invalid runtime unions.
            raise TypeError(f"unsupported dialogue node {type(node)!r}")
    output.append(DIALOGUE_TERMINATOR)
    return bytes(output)


def serialize_dialogue_record(record: DialogueRecord) -> bytes:
    """Serialize marker, bytecode body, and terminator exactly."""

    return DIALOGUE_MARKER + serialize_dialogue_body(record.body)


__all__ = ["serialize_dialogue_body", "serialize_dialogue_record"]
