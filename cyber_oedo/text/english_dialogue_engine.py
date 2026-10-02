"""Native one-byte English dialogue compiler for the rewritten text engine.

The stock `27 28` marker remains the outer record identifier. A translated
record then carries a two-byte English-mode signature and a one-byte glyph
stream. Values 0x80-0xFE are English glyph IDs; low bytes retain the proven
dialogue control language. Japanese records remain valid stock bytecode.

The compiler is intentionally strict about semantic controls. Japanese line
advance opcode 0x40 is presentation and may be recomputed from English word
wrapping. A meaningful control that occurs between two source text runs
requires an explicit translator/runtime timing anchor rather than heuristic
repositioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cyber_oedo.script import ControlCommand, TextRun, parse_dialogue_record
from cyber_oedo.script.opcodes import DIALOGUE_MARKER, DialogueOpcode
from cyber_oedo.text.packed_english import DEFAULT_DISPLAY_CHARACTERS

ENGLISH_MODE_SIGNATURE = bytes((0x7D, 0x45))
ENGLISH_GLYPH_BASE = 0x80
ENGLISH_GLYPH_LAST = 0xFE
ENGLISH_GLYPH_CAPACITY = ENGLISH_GLYPH_LAST - ENGLISH_GLYPH_BASE + 1
ENGLISH_LINE_WIDTH = 22
ENGLISH_VISIBLE_ROWS = 3


class EnglishDialogueCompileError(ValueError):
    """Raised when a record cannot be compiled without semantic guessing."""


@dataclass(frozen=True, slots=True)
class EnglishGlyphTable:
    """Stable one-byte glyph IDs for the native English renderer."""

    characters: str

    def __post_init__(self) -> None:
        if not self.characters:
            raise EnglishDialogueCompileError("glyph table must not be empty")
        if len(set(self.characters)) != len(self.characters):
            raise EnglishDialogueCompileError("glyph table contains duplicates")
        if len(self.characters) > ENGLISH_GLYPH_CAPACITY:
            raise EnglishDialogueCompileError(
                f"glyph table exceeds {ENGLISH_GLYPH_CAPACITY} one-byte IDs"
            )

    @classmethod
    def from_texts(cls, texts: Iterable[str]) -> "EnglishGlyphTable":
        used = set("".join(texts))
        unsupported = used.difference(DEFAULT_DISPLAY_CHARACTERS)
        if unsupported:
            rendered = ", ".join(repr(x) for x in sorted(unsupported))
            raise EnglishDialogueCompileError(
                f"unsupported English display characters: {rendered}"
            )
        ordered = "".join(c for c in DEFAULT_DISPLAY_CHARACTERS if c in used)
        return cls(ordered)

    @property
    def char_to_byte(self) -> dict[str, int]:
        return {
            character: ENGLISH_GLYPH_BASE + index
            for index, character in enumerate(self.characters)
        }

    def encode(self, text: str) -> bytes:
        mapping = self.char_to_byte
        try:
            return bytes(mapping[c] for c in text)
        except KeyError as error:
            raise EnglishDialogueCompileError(
                f"character {error.args[0]!r} is absent from the glyph table"
            ) from error

    def decode(self, data: bytes) -> str:
        chars: list[str] = []
        for value in data:
            index = value - ENGLISH_GLYPH_BASE
            if not 0 <= index < len(self.characters):
                raise EnglishDialogueCompileError(
                    f"invalid English glyph byte ${value:02X}"
                )
            chars.append(self.characters[index])
        return "".join(chars)


def wrap_english(text: str, width: int = ENGLISH_LINE_WIDTH) -> tuple[str, ...]:
    """Word-wrap natural English for the 176-pixel dialogue field."""
    if width <= 0:
        raise EnglishDialogueCompileError("line width must be positive")
    if not text or text.strip() != text or "  " in text:
        raise EnglishDialogueCompileError(
            "English must use single spaces without outer whitespace"
        )
    words = text.split(" ")
    too_wide = [word for word in words if len(word) > width]
    if too_wide:
        raise EnglishDialogueCompileError(
            f"word exceeds {width}-character line: {too_wide[0]!r}"
        )
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def _semantic_mid_controls(source_record: bytes) -> tuple[ControlCommand, ...]:
    record = parse_dialogue_record(source_record, 0)
    if record is None or record.byte_count != len(source_record):
        raise EnglishDialogueCompileError("source record is not valid dialogue bytecode")
    nodes = record.body.nodes
    result: list[ControlCommand] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, ControlCommand):
            continue
        if node.opcode == int(DialogueOpcode.PAGE_BREAK):
            continue
        text_before = any(isinstance(item, TextRun) for item in nodes[:index])
        text_after = any(isinstance(item, TextRun) for item in nodes[index + 1 :])
        if text_before and text_after:
            result.append(node)
    return tuple(result)


def source_requires_manual_anchors(source_record: bytes) -> bool:
    """Return whether semantic controls occur between visible source runs."""
    return bool(_semantic_mid_controls(source_record))


def compile_automatic_record(
    source_record: bytes,
    english: str,
    glyphs: EnglishGlyphTable,
    *,
    width: int = ENGLISH_LINE_WIDTH,
) -> bytes:
    """Compile one record whose semantic controls are only at its boundaries.

    Source line advances are discarded and regenerated from English wrapping.
    All other leading and trailing controls are preserved byte-for-byte.
    """
    record = parse_dialogue_record(source_record, 0)
    if record is None or record.byte_count != len(source_record):
        raise EnglishDialogueCompileError("source record is not valid dialogue bytecode")
    mids = _semantic_mid_controls(source_record)
    if mids:
        opcodes = ", ".join(f"${item.opcode:02X}" for item in mids)
        raise EnglishDialogueCompileError(
            f"record requires explicit semantic control anchors: {opcodes}"
        )

    nodes = record.body.nodes
    first_text = next(
        (i for i, node in enumerate(nodes) if isinstance(node, TextRun)),
        len(nodes),
    )
    last_text = max(
        (i for i, node in enumerate(nodes) if isinstance(node, TextRun)),
        default=-1,
    )

    leading = bytearray()
    trailing = bytearray()
    for index, node in enumerate(nodes):
        if not isinstance(node, ControlCommand):
            continue
        if node.opcode == int(DialogueOpcode.PAGE_BREAK):
            continue
        if index < first_text:
            leading.extend(node.raw)
        elif index > last_text:
            trailing.extend(node.raw)

    lines = wrap_english(english, width)
    body = bytearray(ENGLISH_MODE_SIGNATURE)
    body.extend(leading)
    for index, line in enumerate(lines):
        body.extend(glyphs.encode(line))
        if index < len(lines) - 1:
            body.append(int(DialogueOpcode.PAGE_BREAK))
    body.extend(trailing)
    body.append(0)
    return DIALOGUE_MARKER + bytes(body)


@dataclass(frozen=True, slots=True)
class EnglishEngineAudit:
    total_records: int
    automatic_records: int
    manual_anchor_records: int

    @property
    def automatic_percent(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.automatic_records / self.total_records * 100.0


def audit_source_records(records: Iterable[bytes]) -> EnglishEngineAudit:
    total = automatic = manual = 0
    for record in records:
        total += 1
        if source_requires_manual_anchors(record):
            manual += 1
        else:
            automatic += 1
    return EnglishEngineAudit(total, automatic, manual)
