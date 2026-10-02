"""Native English dialogue compiler for the rewritten text engine.

The stock 27 28 marker remains the outer record identifier. English text is
emitted as self-contained native segments. The stock parser remains responsible
for every proven low-byte control between segments, so voice waits, input waits,
attributes, indirect labels, line advance, and termination keep their original
semantics.

A native segment is:

    7D 45 <one-byte English glyph IDs 80-FE> 7C

The runtime consumes the signature and segment end. Returning to the stock
parser at every segment boundary avoids a persistent English-mode flag and lets
controls remain byte-identical to the Japanese script.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cyber_oedo.script import ControlCommand, TextRun, parse_dialogue_record
from cyber_oedo.script.opcodes import DIALOGUE_MARKER, DialogueOpcode
from cyber_oedo.text.packed_english import DEFAULT_DISPLAY_CHARACTERS

ENGLISH_MODE_SIGNATURE = bytes((0x7D, 0x45))
ENGLISH_SEGMENT_END = 0x7C
ENGLISH_GLYPH_BASE = 0x80
ENGLISH_GLYPH_LAST = 0xFE
ENGLISH_GLYPH_CAPACITY = ENGLISH_GLYPH_LAST - ENGLISH_GLYPH_BASE + 1
ENGLISH_LINE_WIDTH = 22
ENGLISH_VISIBLE_ROWS = 3


class EnglishDialogueCompileError(ValueError):
    """Raised when a record cannot be compiled without semantic guessing."""


@dataclass(frozen=True, slots=True)
class EnglishGlyphTable:
    """Stable one-byte glyph IDs used by native English stream segments."""

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
    """Word-wrap natural English for the 176-pixel fixed-width fallback."""
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


def encode_english_segment(text: str, glyphs: EnglishGlyphTable) -> bytes:
    """Encode one control-free English segment."""
    if not text:
        raise EnglishDialogueCompileError("English segment must not be empty")
    return (
        ENGLISH_MODE_SIGNATURE
        + glyphs.encode(text)
        + bytes((ENGLISH_SEGMENT_END,))
    )


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


def _boundary_controls(
    source_record: bytes,
) -> tuple[bytes, bytes, tuple[ControlCommand, ...]]:
    record = parse_dialogue_record(source_record, 0)
    if record is None or record.byte_count != len(source_record):
        raise EnglishDialogueCompileError("source record is not valid dialogue bytecode")
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
    mids: list[ControlCommand] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, ControlCommand):
            continue
        if node.opcode == int(DialogueOpcode.PAGE_BREAK):
            continue
        if index < first_text:
            leading.extend(node.raw)
        elif index > last_text:
            trailing.extend(node.raw)
        else:
            text_before = any(isinstance(item, TextRun) for item in nodes[:index])
            text_after = any(isinstance(item, TextRun) for item in nodes[index + 1 :])
            if text_before and text_after:
                mids.append(node)
    return bytes(leading), bytes(trailing), tuple(mids)


def _compile_wrapped_text(
    text: str,
    glyphs: EnglishGlyphTable,
    *,
    width: int,
) -> bytes:
    lines = wrap_english(text, width)
    body = bytearray()
    for index, line in enumerate(lines):
        body.extend(encode_english_segment(line, glyphs))
        if index < len(lines) - 1:
            body.append(int(DialogueOpcode.PAGE_BREAK))
    return bytes(body)


def compile_automatic_record(
    source_record: bytes,
    english: str,
    glyphs: EnglishGlyphTable,
    *,
    width: int = ENGLISH_LINE_WIDTH,
) -> bytes:
    """Compile a record with no semantic control between visible source runs."""
    leading, trailing, mids = _boundary_controls(source_record)
    if mids:
        opcodes = ", ".join(f"${item.opcode:02X}" for item in mids)
        raise EnglishDialogueCompileError(
            f"record requires explicit semantic control anchors: {opcodes}"
        )
    body = bytearray(leading)
    body.extend(_compile_wrapped_text(english, glyphs, width=width))
    body.extend(trailing)
    body.append(0)
    return DIALOGUE_MARKER + bytes(body)


def compile_anchored_record(
    source_record: bytes,
    english_fragments: tuple[str, ...],
    glyphs: EnglishGlyphTable,
    *,
    width: int = ENGLISH_LINE_WIDTH,
) -> bytes:
    """Compile one of the semantic-control records with explicit text anchors.

    The number of fragments must be exactly one greater than the number of
    meaningful mid-text source controls. The source controls are copied
    byte-for-byte in their original order between translator-supplied English
    fragments. This prevents timing placement from being inferred by byte
    percentage or Japanese character position.
    """
    leading, trailing, mids = _boundary_controls(source_record)
    if len(english_fragments) != len(mids) + 1:
        raise EnglishDialogueCompileError(
            "anchored record needs exactly one more English fragment than "
            f"semantic mid controls ({len(mids)})"
        )
    if any(not fragment for fragment in english_fragments):
        raise EnglishDialogueCompileError("anchored English fragments must not be empty")

    body = bytearray(leading)
    for index, fragment in enumerate(english_fragments):
        body.extend(_compile_wrapped_text(fragment, glyphs, width=width))
        if index < len(mids):
            body.extend(mids[index].raw)
    body.extend(trailing)
    body.append(0)
    return DIALOGUE_MARKER + bytes(body)


def _source_pacing_positions(source_record: bytes) -> tuple[int, tuple[int, ...]]:
    """Return visible source length and positions of mid-text 2F pauses."""
    record = parse_dialogue_record(source_record, 0)
    if record is None or record.byte_count != len(source_record):
        raise EnglishDialogueCompileError("source record is not valid dialogue bytecode")
    visible = 0
    positions: list[int] = []
    seen_text = False
    nodes = record.body.nodes
    for index, node in enumerate(nodes):
        if isinstance(node, TextRun):
            visible += node.character_count
            seen_text = True
            continue
        if not isinstance(node, ControlCommand):
            continue
        if node.opcode == int(DialogueOpcode.PAGE_BREAK):
            continue
        text_after = any(isinstance(item, TextRun) for item in nodes[index + 1 :])
        if seen_text and text_after:
            if node.opcode != int(DialogueOpcode.TIMED_WAIT):
                raise EnglishDialogueCompileError(
                    "record contains a semantic mid-text control and cannot use "
                    "automatic pacing"
                )
            positions.append(visible)
    return visible, tuple(positions)


def _english_split_candidates(text: str) -> tuple[int, ...]:
    """Return safe English word boundaries for pacing anchors."""
    return tuple(index for index in range(1, len(text)) if text[index] == " ")


def _boundary_score(text: str, boundary: int, target: float) -> tuple[float, float]:
    """Rank a word boundary by punctuation quality, then source-cadence distance."""
    before = text[:boundary].rstrip()
    punctuation_rank = 3.0
    if before.endswith(("...", "…")):
        punctuation_rank = 0.0
    elif before.endswith((".", "?", "!")):
        punctuation_rank = 0.5
    elif before.endswith((";", ":", "—", "–")):
        punctuation_rank = 1.0
    elif before.endswith(","):
        punctuation_rank = 1.5
    distance = abs(boundary - target) / max(1, len(text))
    return punctuation_rank, distance


def pacing_split_points(
    source_record: bytes,
    english: str,
) -> tuple[int, ...]:
    """Map source 2F cadence to natural monotonic English word boundaries.

    This proportional mapping is allowed only for the non-semantic 2F pacing
    control. Voice barriers, indirect text, input waits, and attribute changes
    still require explicit anchors.
    """
    source_length, source_positions = _source_pacing_positions(source_record)
    if not source_positions:
        return ()
    candidates = list(_english_split_candidates(english))
    if len(candidates) < len(source_positions):
        raise EnglishDialogueCompileError(
            "not enough English word boundaries to preserve source pacing pauses"
        )

    chosen: list[int] = []
    minimum_index = 0
    for pause_index, source_position in enumerate(source_positions):
        remaining = len(source_positions) - pause_index - 1
        target = len(english) * source_position / max(1, source_length)
        eligible = candidates[minimum_index : len(candidates) - remaining]
        if not eligible:
            raise EnglishDialogueCompileError("could not place pacing pauses monotonically")
        best = min(
            eligible,
            key=lambda point: _boundary_score(english, point, target),
        )
        chosen.append(best)
        minimum_index = candidates.index(best, minimum_index) + 1
    return tuple(chosen)


def compile_paced_record(
    source_record: bytes,
    english: str,
    glyphs: EnglishGlyphTable,
    *,
    width: int = ENGLISH_LINE_WIDTH,
) -> bytes:
    """Diagnostic-only legacy pacing compiler.

    Definitive Edition release builds MUST use explicit translator-reviewed
    fragments for every mid-text control, including 2F.  This helper is kept
    only to compare historical automatic placements against the frozen anchor
    manifest; it must not be used by the release build.
    """
    leading, trailing, mids = _boundary_controls(source_record)
    if any(command.opcode != int(DialogueOpcode.TIMED_WAIT) for command in mids):
        raise EnglishDialogueCompileError(
            "record contains semantic controls that require explicit anchors"
        )
    split_points = pacing_split_points(source_record, english)
    if len(split_points) != len(mids):
        raise EnglishDialogueCompileError("pacing split count does not match 2F count")

    fragments: list[str] = []
    start = 0
    for point in split_points:
        fragment = english[start:point].strip()
        if not fragment:
            raise EnglishDialogueCompileError("pacing split produced an empty fragment")
        fragments.append(fragment)
        start = point
    tail = english[start:].strip()
    if not tail:
        raise EnglishDialogueCompileError("pacing split produced an empty final fragment")
    fragments.append(tail)

    body = bytearray(leading)
    for index, fragment in enumerate(fragments):
        body.extend(_compile_wrapped_text(fragment, glyphs, width=width))
        if index < len(mids):
            body.extend(mids[index].raw)
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
