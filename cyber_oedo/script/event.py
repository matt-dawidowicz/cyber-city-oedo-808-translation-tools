"""Mission 0-B event-script layout: parse, then relink offsets after edits.

Named resources that carry scenes and conversations (``KURUZER``,
``ZAKO0001``, ...) hold a small event program.  After the 16-byte header that
the loader strips, the resident body is:

``entry table``
    7-byte entries: five condition bytes, then a big-endian offset measured
    from that offset field.  Entry 0 (``FF FE 00 FF FE``) points at the script
    start; other entries point at per-topic handlers.  The table ends at the
    first entry whose first two bytes are zero; that entry's offset points at
    the label table (walker ``$9E39``).
``label table``
    14-byte topic labels (flag byte + 13-byte Shift-JIS name), kept verbatim.
``script``
    Commands dispatched from the 27-entry table at ``$9048``, each handler
    ending at a ``00`` byte.  The script pointer is ``$7F/$80``; ``$9F11``
    reads and ``$9F14`` advances.

Every pointer movement is relative, so edits only require recomputing
offset fields:

* ``24`` IF: expression, then a big-endian offset applied when false;
* ``2D`` GOTO: big-endian offset;
* ``32`` rotating choice: three bytes (index, last index, wrap mode), then
  ``last index + 1`` blocks, each prefixed with its big-endian length.

All offsets are measured from the byte after the offset field, except entry
table offsets, which are measured from the field itself.  The interpreter's
handlers and operand helpers are source-guarded in ``verify_event_interpreter``.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.named_resources import MISSION0_B_MODULE_BASE, RESOURCE_HEADER_BYTES
from cyber_oedo.text.extract_dialogue import parse_record

ENTRY_SIZE = 7
ENTRY_OFFSET_FIELD = 5
SCRIPT_ENTRY_PREFIX = bytes.fromhex("FF FE 00 FF FE")
END = 0x00
DIALOGUE = 0x27
DIALOGUE_SECOND = 0x28
EXPRESSION_END = 0x26

# Command operand shapes from the $9048 dispatch table.
_VALUE = 3  # $962B: tag byte, then big-endian word (tag 01 = variable)
FIXED_OPERANDS = {
    0x22: 2, 0x23: 2,                       # word (variable index)
    0x2E: 1, 0x3B: 1, 0x38: 1, 0x3C: 1, 0x2F: 1,
    0x2B: 0, 0x35: 0, 0x4B: 0,
    0x33: _VALUE, 0x34: _VALUE, 0x44: _VALUE, 0x47: _VALUE,
    0x46: 3 * _VALUE, 0x49: 4 * _VALUE, 0x4A: 5 * _VALUE,
}
# 48 ($941F) reads two values, and a third only when the second's low byte
# is 2.  The count is static only when that second value is an immediate.
CONDITIONAL_VALUE_OPCODE = 0x48
VARIABLE_TAG = 0x01
# Expression tokens from the $97D1 table; 26 terminates the expression.
EXPRESSION_OPERANDS = {
    0x01: 2, 0x03: 2, 0x31: 2, 0x2F: 2, 0x37: 2, 0x3F: 1,
    **{op: 0 for op in (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16,
                        0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x3B)},
}

# Interpreter source guards: dispatch table, operand helpers and the
# pointer-moving handlers whose semantics this module relies on.
INTERPRETER_GUARDS = (
    ("opcode table", 0x9048, bytes.fromhex(
        "329C90 307391 229491 23A491 2E7494 3B8094 388C94 3C9894 2FA494 2BB094"
        " 06CC94 24E294 2D1695 273495 3A5996 360397 33A792 34CB92 356494"
        " 440994 46B693 481F94 4B5994 49B791 477E93 4ADF92 4C0292 00")),
    ("expression table", 0x97D1, bytes.fromhex(
        "011098 031A98 312998 2F5198 373D98 3F6598 10A298 11C198 12E098"
        " 131B99 196C99 1BA299 1AD899 1C0E9A 1D449A 14789A 15929A 1EB09A"
        " 16E49A 3B6B99 00")),
    ("fetch/advance", 0x9F11, bytes.fromhex("B2 7F 60 E6 7F D0 02 E6 80 60")),
    ("word operand", 0x9648, bytes.fromhex("20 11 9F 20 14 9F 85 01 20 11 9F 20 14 9F 85 00 60")),
    ("value operand", 0x962B, bytes.fromhex("20 11 9F 20 14 9F C9 01 F0 0C 20 48 96")),
    ("IF handler", 0x94E2, bytes.fromhex("20 AC 97 A5 03 C9 00 D0 04 A5 02 C9 00 F0 07 20 14 9F 20 14 9F 60")),
    ("GOTO handler", 0x9516, bytes.fromhex("20 11 9F 20 14 9F 85 01 20 11 9F 20 14 9F 85 00 A5 7F 18 65 00")),
    ("dialogue handler", 0x9534, bytes.fromhex("20 11 9F 20 14 9F C9 28 D0 04 20 43 95 60")),
    ("choice block skip", 0x90F9, bytes.fromhex("A5 7F 48 A5 80 48 20 11 9F 85 05 20 14 9F 20 11 9F 85 04")),
    ("entry table walk", 0x9E3C, bytes.fromhex("A0 01 B1 0E 12 0E F0 0F A5 0E 18 69 07")),
)


class EventScriptError(ValueError):
    """Raised when a resource body does not follow the decoded event layout."""


@dataclass(frozen=True, slots=True)
class OffsetField:
    """One big-endian offset: value == target - base (16-bit wraparound)."""

    field: int
    base: int
    target: int
    kind: str


@dataclass(frozen=True, slots=True)
class DialogueSpan:
    """One ``27 28 ... 00`` dialogue record inside the script."""

    start: int
    end: int  # exclusive, after the terminator


@dataclass(frozen=True, slots=True)
class EventLayout:
    """Parsed structure of one resident resource body."""

    body: bytes
    script_start: int
    label_start: int
    tail_start: int
    boundaries: frozenset[int]
    offsets: tuple[OffsetField, ...]
    dialogue: tuple[DialogueSpan, ...]


def verify_event_interpreter(payload: bytes | memoryview) -> None:
    for label, cpu, expected in INTERPRETER_GUARDS:
        start = MISSION0_B_MODULE_BASE + cpu
        if bytes(payload[start : start + len(expected)]) != expected:
            raise EventScriptError(f"Mission 0-B event {label} at ${cpu:04X} differs from source")


def _word(body: bytes, at: int) -> int:
    if at + 2 > len(body):
        raise EventScriptError(f"offset field at 0x{at:04X} runs past the body")
    return int.from_bytes(body[at : at + 2], "big")


def _relative(body: bytes, field: int, base: int, kind: str) -> OffsetField:
    target = (base + _word(body, field)) & 0xFFFF
    return OffsetField(field, base, target, kind)


class _Parser:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.boundaries: set[int] = set()
        self.offsets: list[OffsetField] = []
        self.dialogue: list[DialogueSpan] = []

    def expression(self, at: int, end: int) -> int:
        while True:
            if at >= end:
                raise EventScriptError("expression runs past its block")
            token = self.body[at]
            at += 1
            if token == EXPRESSION_END:
                return at
            if token not in EXPRESSION_OPERANDS:
                raise EventScriptError(f"unknown expression token 0x{token:02X} at 0x{at - 1:04X}")
            at += EXPRESSION_OPERANDS[token]

    def command(self, at: int, end: int) -> int:
        body = self.body
        self.boundaries.add(at)
        op = body[at]
        at += 1
        if op == END:
            return at
        if op in FIXED_OPERANDS:
            return at + FIXED_OPERANDS[op]
        if op == CONDITIONAL_VALUE_OPCODE:
            second = at + _VALUE
            if second + _VALUE > end:
                raise EventScriptError("command 48 runs past its block")
            if body[second] == VARIABLE_TAG:
                raise EventScriptError(f"command 48 at 0x{at - 1:04X} has a variable-dependent length")
            return second + _VALUE + (_VALUE if body[second + 2] == 2 else 0)
        if op == DIALOGUE:
            if at >= end:
                raise EventScriptError("dialogue command runs past its block")
            if body[at] != DIALOGUE_SECOND:
                return at + 1
            if end - at - 1 <= 0:
                raise EventScriptError(f"dialogue record at 0x{at - 1:04X} has no body")
            record = parse_record(body, at + 1, limit=end - at - 1, allow_unknown_controls=False)
            if record is None:
                raise EventScriptError(f"unparseable dialogue record at 0x{at - 1:04X}")
            stop = record.end_offset + 1
            self.dialogue.append(DialogueSpan(at - 1, stop))
            return stop
        if op == 0x06:
            return self.expression(at + 2, end)
        if op == 0x4C:
            return self.expression(self.expression(at, end), end)
        if op == 0x24:
            field = self.expression(at, end)
            self.offsets.append(_relative(body, field, field + 2, "if"))
            return field + 2
        if op == 0x2D:
            self.offsets.append(_relative(body, at, at + 2, "goto"))
            return at + 2
        if op in (0x3A, 0x36, 0x30):
            nul = body.find(b"\0", at, end)
            if nul < 0:
                raise EventScriptError(f"unterminated name after 0x{op:02X} at 0x{at - 1:04X}")
            # 30 leaves the pointer on the NUL, which then ends the handler.
            return nul if op == 0x30 else nul + 1
        if op == 0x32:
            if at + 3 > end:
                raise EventScriptError("choice command runs past its block")
            blocks = body[at + 1] + 1
            at += 3
            for _ in range(blocks):
                length = _word(body, at)
                block_end = at + 2 + length
                if block_end > end:
                    raise EventScriptError(f"choice block at 0x{at:04X} runs past its parent")
                self.offsets.append(OffsetField(at, at + 2, block_end, "choice"))
                self.sequence(at + 2, block_end)
                at = block_end
            self.boundaries.add(at)
            return at
        raise EventScriptError(f"unknown event opcode 0x{op:02X} at 0x{at - 1:04X}")

    def sequence(self, at: int, end: int) -> None:
        while at < end:
            at = self.command(at, end)
        if at != end:
            raise EventScriptError(f"command overruns block end 0x{end:04X}")
        self.boundaries.add(end)

    def top_level(self, at: int, end: int) -> int:
        """Parse handlers to the end; return where opaque alignment tail starts.

        Descriptor lengths are 16-byte multiples, so up to 15 stale bytes may
        follow the last handler's ``00``, sometimes a cut-off copy of a
        handler.  They are never executed and are kept verbatim.
        """

        checkpoint = None
        while at < end:
            try:
                start = at
                at = self.command(at, end)
            except (EventScriptError, IndexError):
                if checkpoint is not None and end - checkpoint[0] < 16:
                    tail, boundaries, offsets, dialogue = checkpoint
                    self.boundaries = boundaries
                    del self.offsets[offsets:]
                    del self.dialogue[dialogue:]
                    return tail
                raise
            if self.body[start] == END:
                checkpoint = (at, set(self.boundaries), len(self.offsets), len(self.dialogue))
        self.boundaries.add(end)
        return end


def parse_event_body(body: bytes) -> EventLayout:
    """Parse a resident body (resource bytes after the 16-byte header)."""

    if body[:ENTRY_OFFSET_FIELD] != SCRIPT_ENTRY_PREFIX:
        raise EventScriptError("body does not start with the script entry")
    entries: list[OffsetField] = []
    at = 0
    while True:
        if at + ENTRY_SIZE > len(body):
            raise EventScriptError("entry table has no terminator")
        field = at + ENTRY_OFFSET_FIELD
        kind = "entry" if body[at] or body[at + 1] else "labels"
        entries.append(_relative(body, field, field, kind))
        at += ENTRY_SIZE
        if kind == "labels":
            break
    script_start = entries[0].target
    label_start = entries[-1].target
    if not at <= label_start <= script_start <= len(body):
        raise EventScriptError("entry table, labels and script are out of order")

    parser = _Parser(body)
    tail_start = parser.top_level(script_start, len(body))
    for row in entries[:-1]:
        if row.target not in parser.boundaries:
            raise EventScriptError(f"entry offset at 0x{row.field:04X} does not hit a command")
    for row in parser.offsets:
        if row.target not in parser.boundaries:
            raise EventScriptError(f"{row.kind} offset at 0x{row.field:04X} does not hit a command")
    return EventLayout(
        body=body,
        script_start=script_start,
        label_start=label_start,
        tail_start=tail_start,
        boundaries=frozenset(parser.boundaries),
        offsets=tuple(entries) + tuple(parser.offsets),
        dialogue=tuple(parser.dialogue),
    )


def parse_event_resource(resource: bytes) -> EventLayout:
    return parse_event_body(resource[RESOURCE_HEADER_BYTES:])


def rebuild_event_resource(resource: bytes, replacements: dict[int, bytes]) -> bytes:
    """Return a whole resource (header kept) with dialogue replaced and relinked."""

    layout = parse_event_resource(resource)
    return resource[:RESOURCE_HEADER_BYTES] + replace_dialogue(layout, replacements)


def doubled_dialogue(layout: EventLayout, *, page_break: bool = True) -> dict[int, bytes]:
    """Diagnostic replacements: every record's body twice.

    With *page_break* the copies are separated by a ``40`` button wait;
    without it they run on, so fixed-frame controller input stays in step.
    """

    separator = b"\x40" if page_break else b""
    out = {}
    for span in layout.dialogue:
        body = layout.body[span.start + 2 : span.end - 1]
        out[span.start] = bytes((DIALOGUE, DIALOGUE_SECOND)) + body + separator + body + b"\0"
    return out


def replace_dialogue(layout: EventLayout, replacements: dict[int, bytes]) -> bytes:
    """Return the body with dialogue records replaced and offsets relinked.

    *replacements* maps a record's body offset (its ``27`` byte) to complete
    new ``27 28 ... 00`` bytes.  Every offset field is rewritten so it still
    reaches the same command after records change size.
    """

    by_start = {span.start: span for span in layout.dialogue}
    unknown = sorted(set(replacements) - set(by_start))
    if unknown:
        raise EventScriptError(f"no dialogue record starts at {[hex(x) for x in unknown]}")
    for start, record in replacements.items():
        if not (record.startswith(bytes((DIALOGUE, DIALOGUE_SECOND))) and record.endswith(b"\0")):
            raise EventScriptError(f"replacement at 0x{start:04X} is not a 27 28 ... 00 record")

    edits = [(by_start[start], replacements[start]) for start in sorted(replacements)]

    def moved(position: int) -> int:
        shift = 0
        for span, record in edits:
            if position >= span.end:
                shift += len(record) - (span.end - span.start)
            elif position > span.start:
                raise EventScriptError(f"offset target 0x{position:04X} is inside an edited record")
        return position + shift

    out = bytearray()
    cursor = 0
    for span, record in edits:
        out += layout.body[cursor : span.start] + record
        cursor = span.end
    out += layout.body[cursor:]

    for row in layout.offsets:
        value = (moved(row.target) - moved(row.base)) & 0xFFFF
        if row.kind == "choice" and moved(row.target) < moved(row.base):
            raise EventScriptError("choice block length became negative")
        field = moved(row.field)
        out[field : field + 2] = value.to_bytes(2, "big")
    return bytes(out)
