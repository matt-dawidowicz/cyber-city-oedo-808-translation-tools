"""Typed dialogue-script parsing and lossless serialization primitives."""

from .ast import ControlCommand, DialogueBody, DialogueRecord, TextRun
from .opcodes import (
    DIALOGUE_MARKER,
    DIALOGUE_TERMINATOR,
    DialogueOpcode,
    OpcodeSpec,
    OPCODE_SPECS,
)
from .parser import parse_dialogue_body, parse_dialogue_record
from .serializer import serialize_dialogue_body, serialize_dialogue_record

__all__ = [
    "ControlCommand",
    "DIALOGUE_MARKER",
    "DIALOGUE_TERMINATOR",
    "DialogueBody",
    "DialogueOpcode",
    "DialogueRecord",
    "OpcodeSpec",
    "OPCODE_SPECS",
    "TextRun",
    "parse_dialogue_body",
    "parse_dialogue_record",
    "serialize_dialogue_body",
    "serialize_dialogue_record",
]
