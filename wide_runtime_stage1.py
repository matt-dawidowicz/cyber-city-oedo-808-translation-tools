"""Build the first runtime-test patch for the proposed English escape stream.

Stage 1 proves only parser entry/exit and literal one-byte ASCII transport.
It maps the small test alphabet back to the original 16x16 Shift-JIS glyph
path.  It intentionally does not crop fonts, alter tile uploads, or claim a
22-column display; those changes require Stage 1 emulator evidence first.
"""

from __future__ import annotations

from dataclasses import dataclass


WIDE_START = 0xFF
WIDE_TAG = 0x00
WIDE_END = 0xFE
MISSION0_MODULE_PAYLOAD_BASE = 0x00131800
MISSION0_PARSER_HOOK_CPU = 0x95D4
MISSION0_GLYPH_HOOK_CPU = 0x56C0
MISSION0_CODE_CAVE_CPU = 0x9F1B
MISSION0_CODE_CAVE_SIZE = 0xE5
PARSER_RESTART_CPU = 0x9543
ORIGINAL_GLYPH_CONTINUATION_CPU = 0x95D8
STREAM_READ_CPU = 0x9F11
STREAM_ADVANCE_CPU = 0x9F14
CHARACTER_DELAY_CPU = 0x8CFC
RENDER_CELL_CPU = 0x5915
BIOS_GET_FONT_CPU = 0xE060
GLYPH_LEAD_ZERO_PAGE = 0xF9
GLYPH_TRAIL_ZERO_PAGE = 0xF8
TEST_ALPHABET = frozenset(b" ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


@dataclass(frozen=True, slots=True)
class RuntimePatch:
    """Describe one source-guarded payload replacement for Stage 1."""

    cpu_address: int
    expected: bytes
    replacement: bytes
    label: str

    def __post_init__(self) -> None:
        """Reject malformed patch coordinates and unequal guard sizes."""

        if not 0 <= self.cpu_address < 0xA000:
            raise ValueError("runtime patch CPU address must be below 0xA000")
        if not self.expected or len(self.expected) != len(self.replacement):
            raise ValueError("runtime patch guard and replacement must match")

    @property
    def payload_offset(self) -> int:
        """Return the Track 2 payload coordinate for the CPU patch address."""

        return MISSION0_MODULE_PAYLOAD_BASE + self.cpu_address


class _Assembler:
    """Assemble the limited HuC6280 instruction subset used by Stage 1."""

    def __init__(self, origin: int) -> None:
        """Start a routine at a bounded CPU origin."""

        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[str, int, str]] = []

    @property
    def address(self) -> int:
        """Return the CPU address immediately following emitted code."""

        return self.origin + len(self.code)

    def emit(self, *values: int) -> None:
        """Append byte-sized opcode or operand values."""

        if any(not 0 <= value <= 0xFF for value in values):
            raise ValueError("assembly byte lies outside 0x00..0xFF")
        self.code.extend(values)

    def label(self, name: str) -> None:
        """Name the current instruction address exactly once."""

        if name in self.labels:
            raise ValueError(f"duplicate assembly label: {name}")
        self.labels[name] = self.address

    def immediate(self, opcode: int, value: int) -> None:
        """Emit an immediate two-byte instruction."""

        self.emit(opcode, value)

    def zero_page(self, opcode: int, address: int) -> None:
        """Emit a zero-page two-byte instruction."""

        self.emit(opcode, address)

    def absolute(self, opcode: int, address: int) -> None:
        """Emit a three-byte absolute instruction."""

        self.emit(opcode, address & 0xFF, address >> 8)

    def branch(self, opcode: int, target: str) -> None:
        """Emit a relative branch and defer its signed offset."""

        self.emit(opcode, 0)
        self.fixups.append(("relative", len(self.code) - 1, target))

    def absolute_label(self, opcode: int, target: str) -> None:
        """Emit an absolute target placeholder resolved at finish time."""

        self.emit(opcode, 0, 0)
        self.fixups.append(("absolute", len(self.code) - 2, target))

    def finish(self) -> bytes:
        """Resolve labels and return immutable machine code."""

        for kind, position, target in self.fixups:
            if target not in self.labels:
                raise ValueError(f"unknown assembly label: {target}")
            address = self.labels[target]
            if kind == "absolute":
                self.code[position] = address & 0xFF
                self.code[position + 1] = address >> 8
                continue
            displacement = address - (self.origin + position + 1)
            if not -128 <= displacement <= 127:
                raise ValueError(f"branch to {target} is out of range")
            self.code[position] = displacement & 0xFF
        return bytes(self.code)


def encode_stage1_field(text: str, footprint: int) -> bytes:
    """Encode one exact-footprint Stage 1 field without ambiguous padding.

    Only capital letters, digits, and spaces are accepted.  Requiring the
    escape block to consume the entire source field makes ``WIDE_END`` land
    directly before the original command or terminator; the parser never has
    to interpret hypothetical filler bytes after leaving escape mode.
    """

    if not isinstance(text, str) or not text:
        raise ValueError("Stage 1 text must be a non-empty string")
    if text != text.strip() or "  " in text:
        raise ValueError("Stage 1 text must use single interior spaces")
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("Stage 1 text must be ASCII") from error
    if any(byte not in TEST_ALPHABET for byte in encoded):
        raise ValueError("Stage 1 text uses an unsupported test glyph")
    stream = bytes((WIDE_START, WIDE_TAG)) + encoded + bytes((WIDE_END,))
    if not isinstance(footprint, int) or isinstance(footprint, bool):
        raise ValueError("Stage 1 footprint must be an integer")
    if len(stream) != footprint:
        raise ValueError(
            "Stage 1 stream must exactly occupy the tested source field: "
            f"{len(stream)} != {footprint}"
        )
    return stream


def _emit_parser_dispatch(assembler: _Assembler) -> None:
    """Emit the escape-loop parser while preserving every non-escape byte."""

    assembler.label("parser_dispatch")
    assembler.immediate(0xC9, WIDE_START)  # CMP #$FF
    assembler.branch(0xD0, "normal_stream")  # BNE
    assembler.emit(0xB2, 0x7F)  # LDA ($7F), peek without consuming it.
    assembler.immediate(0xC9, WIDE_TAG)  # CMP #$00
    assembler.branch(0xD0, "ordinary_ff")  # BNE
    assembler.absolute(0x20, STREAM_ADVANCE_CPU)  # Consume tag only.
    assembler.branch(0x80, "wide_loop")  # BRA

    assembler.label("ordinary_ff")
    assembler.immediate(0xA9, WIDE_START)  # Restore original stream byte.
    assembler.label("normal_stream")
    assembler.immediate(0xC9, 0x80)  # Recreate overwritten stock comparison.
    assembler.branch(0xF0, "parser_restart")  # BEQ
    assembler.absolute(0x4C, ORIGINAL_GLYPH_CONTINUATION_CPU)  # JMP $95D8
    assembler.label("parser_restart")
    assembler.absolute(0x4C, PARSER_RESTART_CPU)  # JMP $9543

    assembler.label("wide_loop")
    assembler.absolute(0x20, STREAM_READ_CPU)  # JSR $9F11
    assembler.absolute(0x20, STREAM_ADVANCE_CPU)  # JSR $9F14
    assembler.immediate(0xC9, WIDE_END)  # CMP #$FE
    assembler.branch(0xF0, "parser_restart")  # BEQ
    assembler.zero_page(0x85, 0x03)  # STA $03, stock left-glyph input.
    assembler.absolute(0x20, CHARACTER_DELAY_CPU)  # JSR $8CFC
    assembler.absolute_label(0x20, "render_wide_cell")
    assembler.branch(0x80, "wide_loop")  # BRA

    assembler.label("render_wide_cell")
    assembler.absolute(0x20, RENDER_CELL_CPU)  # JSR $5915
    assembler.emit(0x60)  # RTS


def _emit_glyph_hook(assembler: _Assembler) -> None:
    """Map Stage 1 literal ASCII to stock fullwidth Shift-JIS glyphs.

    The stage deliberately leaves the original font bitmap and 16-pixel cursor
    advance untouched.  A Japanese lead byte is at least ``0x80``, while the
    restricted Stage 1 text byte is below that threshold, so the hook's range
    test preserves normal Shift-JIS rendering.
    """

    assembler.label("glyph_hook")
    assembler.zero_page(0xA5, GLYPH_LEAD_ZERO_PAGE)  # LDA $F9
    assembler.immediate(0xC9, 0x20)  # CMP #space
    assembler.branch(0xF0, "wide_space")  # BEQ
    assembler.immediate(0xC9, 0x30)  # CMP #digit start
    assembler.branch(0x90, "normal_glyph")  # BCC
    assembler.immediate(0xC9, 0x3A)  # CMP after digit end
    assembler.branch(0x90, "wide_alphanumeric")  # BCC
    assembler.immediate(0xC9, 0x41)  # CMP uppercase start
    assembler.branch(0x90, "normal_glyph")  # BCC
    assembler.immediate(0xC9, 0x5B)  # CMP after uppercase end
    assembler.branch(0xB0, "normal_glyph")  # BCS

    assembler.label("wide_alphanumeric")
    assembler.emit(0x18)  # CLC
    assembler.immediate(0x69, 0x1F)  # ADC #$1F, ASCII to SJIS trail.
    assembler.zero_page(0x85, GLYPH_TRAIL_ZERO_PAGE)  # STA $F8
    assembler.immediate(0xA9, 0x82)  # LDA #SJIS lead
    assembler.zero_page(0x85, GLYPH_LEAD_ZERO_PAGE)  # STA $F9
    assembler.absolute(0x20, BIOS_GET_FONT_CPU)  # JSR $E060
    assembler.emit(0x58, 0x60)  # CLI; RTS, matching stock post-call timing.

    assembler.label("wide_space")
    assembler.immediate(0xA9, 0x40)  # LDA fullwidth-space trail
    assembler.zero_page(0x85, GLYPH_TRAIL_ZERO_PAGE)  # STA $F8
    assembler.immediate(0xA9, 0x81)  # LDA fullwidth-space lead
    assembler.zero_page(0x85, GLYPH_LEAD_ZERO_PAGE)  # STA $F9
    assembler.absolute(0x20, BIOS_GET_FONT_CPU)  # JSR $E060
    assembler.emit(0x58, 0x60)  # CLI; RTS

    assembler.label("normal_glyph")
    assembler.absolute(0x4C, BIOS_GET_FONT_CPU)  # JMP $E060


def build_stage1_runtime_patches() -> tuple[RuntimePatch, ...]:
    """Return the three guarded parser/glyph/cave patches for Stage 1."""

    assembler = _Assembler(MISSION0_CODE_CAVE_CPU)
    _emit_parser_dispatch(assembler)
    _emit_glyph_hook(assembler)
    code = assembler.finish()
    if len(code) > MISSION0_CODE_CAVE_SIZE:
        raise ValueError("Stage 1 runtime exceeds the historical cave size")
    cave = code.ljust(MISSION0_CODE_CAVE_SIZE, b"\x00")
    glyph_hook = assembler.labels["glyph_hook"]
    return (
        RuntimePatch(
            MISSION0_PARSER_HOOK_CPU,
            bytes.fromhex("C9 80 F0"),
            bytes((0x20, MISSION0_CODE_CAVE_CPU & 0xFF,
                   MISSION0_CODE_CAVE_CPU >> 8)),
            "Stage 1 literal-English parser hook",
        ),
        RuntimePatch(
            MISSION0_GLYPH_HOOK_CPU,
            bytes.fromhex("20 60 E0"),
            bytes((0x20, glyph_hook & 0xFF, glyph_hook >> 8)),
            "Stage 1 ASCII-to-Shift-JIS glyph hook",
        ),
        RuntimePatch(
            MISSION0_CODE_CAVE_CPU,
            b"\x00" * MISSION0_CODE_CAVE_SIZE,
            cave,
            "Stage 1 parser and glyph routine",
        ),
    )
