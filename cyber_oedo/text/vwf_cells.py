"""Cell-packed variable-width English dialogue compiler.

The stock dialogue grid is 11 16-pixel cells wide.  Instead of replacing that
proven cursor/redraw/scroll machinery, VWF mode packs as many proportional
English glyphs as fit into each 16-pixel cell.

A VWF cell is represented by a 16-bit token in the existing two-byte cell
buffer.  Tokens index a per-mission dictionary of fixed-size glyph descriptors.
The runtime font hook can therefore reconstruct the same 16x16 cell both when
it is first typed and when the stock engine redraws or scrolls it.

This is intentionally different from the fixed 8x16 fallback:
- fixed mode: two 8-pixel glyphs per 16-pixel cell;
- VWF mode: 1..MAX_CELL_GLYPHS proportional glyphs per cell.

The compiler uses pixel-width wrapping at 176 pixels / 11 stock cells.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.vwf_text import LINE_PIXELS, VwfFont, measure_text, wrap_vwf

VWF_MODE_SIGNATURE = bytes((0x7D, 0x56))
VWF_SEGMENT_END_TOKEN = 0xFFFF
# Stored VWF cells use first bytes $01-$1F. Stock Japanese glyph cells never
# use that range, and fixed native-English cells use $20-$7E, so redraw can
# identify VWF without a transient parser flag.
VWF_TOKEN_FIRST_MIN = 0x01
# Super System Card ownership is deliberately disjoint:
#   $68-$72 maintained fast-load/cache stack
#   $73-$7B pre-rendered authored VWF cells
#   $7C-$7F external English stream pool
# At 32 bytes per cell, each 8 KiB VWF bank owns exactly 256 tokens.
VWF_CARD_RAM_BASE_BANK = 0x73
VWF_CARD_RAM_BANK_COUNT = 9
VWF_TOKEN_FIRST_MAX = VWF_TOKEN_FIRST_MIN + VWF_CARD_RAM_BANK_COUNT - 1
VWF_TOKEN_CAPACITY = VWF_CARD_RAM_BANK_COUNT * 0x100
VWF_STAGED_CELL_BYTES = 32
VWF_CELL_PIXELS = 16
VWF_CELLS_PER_LINE = LINE_PIXELS // VWF_CELL_PIXELS
MAX_CELL_GLYPHS = 6
VWF_DESCRIPTOR_BYTES = 1 + MAX_CELL_GLYPHS
VWF_DESCRIPTOR_PAD = 0xFF


class VwfCellCompileError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VwfCellDescriptor:
    glyph_ids: tuple[int, ...]
    pixel_width: int

    def __post_init__(self) -> None:
        if not 1 <= len(self.glyph_ids) <= MAX_CELL_GLYPHS:
            raise VwfCellCompileError("VWF cell glyph count is outside supported range")
        if not 1 <= self.pixel_width <= VWF_CELL_PIXELS:
            raise VwfCellCompileError("VWF cell width must be 1..16 pixels")
        if any(not 0 <= glyph_id <= 0xFE for glyph_id in self.glyph_ids):
            raise VwfCellCompileError("VWF glyph ID must fit one byte and avoid pad FF")

    def encode(self) -> bytes:
        payload = bytes((len(self.glyph_ids),)) + bytes(self.glyph_ids)
        return payload + bytes((VWF_DESCRIPTOR_PAD,)) * (
            VWF_DESCRIPTOR_BYTES - len(payload)
        )


@dataclass(frozen=True, slots=True)
class VwfCellDictionary:
    descriptors: tuple[VwfCellDescriptor, ...]

    def __post_init__(self) -> None:
        if len(self.descriptors) > VWF_TOKEN_CAPACITY:
            raise VwfCellCompileError(
                f"VWF dictionary exceeds {VWF_TOKEN_CAPACITY} self-identifying tokens"
            )

    @property
    def encoded(self) -> bytes:
        return b"".join(item.encode() for item in self.descriptors)


@dataclass(frozen=True, slots=True)
class VwfCompiledLine:
    text: str
    tokens: tuple[int, ...]
    pixel_width: int

    def __post_init__(self) -> None:
        if len(self.tokens) > VWF_CELLS_PER_LINE:
            raise VwfCellCompileError("VWF line exceeds stock 11-cell grid")


@dataclass(frozen=True, slots=True)
class VwfCompiledText:
    lines: tuple[VwfCompiledLine, ...]
    dictionary: VwfCellDictionary

    @property
    def stream(self) -> bytes:
        out = bytearray()
        for line_index, line in enumerate(self.lines):
            out.extend(VWF_MODE_SIGNATURE)
            for token in line.tokens:
                out.extend(encode_vwf_token(token))
            out.extend(VWF_SEGMENT_END_TOKEN.to_bytes(2, "big"))
            if line_index < len(self.lines) - 1:
                out.append(0x40)
        return bytes(out)


class VwfDictionaryBuilder:
    def __init__(self) -> None:
        self._rows: list[VwfCellDescriptor] = []
        self._by_glyphs: dict[tuple[int, ...], int] = {}

    def token(self, descriptor: VwfCellDescriptor) -> int:
        key = descriptor.glyph_ids
        existing = self._by_glyphs.get(key)
        if existing is not None:
            return existing
        token = len(self._rows)
        if token >= VWF_TOKEN_CAPACITY:
            raise VwfCellCompileError("VWF self-identifying token space exhausted")
        self._rows.append(descriptor)
        self._by_glyphs[key] = token
        return token

    def finish(self) -> VwfCellDictionary:
        return VwfCellDictionary(tuple(self._rows))


def encode_vwf_token(token: int) -> bytes:
    """Encode a dictionary index as one redraw-safe two-byte cell token."""
    if not 0 <= token < VWF_TOKEN_CAPACITY:
        raise VwfCellCompileError("VWF token lies outside self-identifying range")
    first = VWF_TOKEN_FIRST_MIN + (token >> 8)
    second = token & 0xFF
    return bytes((first, second))


def decode_vwf_token(raw: bytes) -> int:
    """Decode a stored VWF cell token and reject non-VWF cell bytes."""
    if len(raw) != 2:
        raise VwfCellCompileError("stored VWF token must contain two bytes")
    first, second = raw
    if not VWF_TOKEN_FIRST_MIN <= first <= VWF_TOKEN_FIRST_MAX:
        raise VwfCellCompileError("stored cell is not a VWF token")
    return ((first - VWF_TOKEN_FIRST_MIN) << 8) | second


def _cell_width(text: str, font: VwfFont) -> int:
    return measure_text(text, font)


def _split_vwf_cells(text: str, font: VwfFont) -> tuple[str, ...]:
    """Split one line into stock 16-pixel cells without allocating tokens."""
    if not text:
        raise VwfCellCompileError("VWF line must not be empty")
    cells: list[str] = []
    current = ""
    for character in text:
        candidate = current + character
        if current and (
            len(candidate) > MAX_CELL_GLYPHS
            or _cell_width(candidate, font) > VWF_CELL_PIXELS
        ):
            # Carry overflow whitespace into the following cell unchanged.
            cells.append(current)
            current = character
        else:
            current = candidate
        if _cell_width(current, font) > VWF_CELL_PIXELS:
            raise VwfCellCompileError(
                f"single VWF glyph/cluster exceeds {VWF_CELL_PIXELS}px: {current!r}"
            )
    if current:
        cells.append(current)
    return tuple(cells)


def wrap_vwf_cells(text: str, font: VwfFont) -> tuple[str, ...]:
    """Wrap authored dialogue against BOTH pixels and stock redraw cells.

    A 176-pixel line may still exceed the 11-cell stock grid if many glyphs
    cannot share a cell. Avoid emitting a wider stream that fails only after
    partially allocating its mission dictionary.
    """
    # Delegate whitespace, font-repertoire, and unbreakable-pixel validation
    # to the canonical proportional wrapper.
    wrap_vwf(text, font, max_pixels=LINE_PIXELS)
    words = text.split(" ")
    lines: list[str] = []
    current = words[0]
    for word in words:
        if len(_split_vwf_cells(word, font)) > VWF_CELLS_PER_LINE:
            raise VwfCellCompileError(
                f"word exceeds the {VWF_CELLS_PER_LINE}-cell stock grid: {word!r}"
            )
    for word in words[1:]:
        candidate = current + " " + word
        if (
            measure_text(candidate, font) <= LINE_PIXELS
            and len(_split_vwf_cells(candidate, font)) <= VWF_CELLS_PER_LINE
        ):
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def pack_vwf_line(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
    dictionary: VwfDictionaryBuilder,
) -> VwfCompiledLine:
    """Pack one already-wrapped line into <=11 proportional 16-pixel cells."""

    cells = _split_vwf_cells(text, font)
    if len(cells) > VWF_CELLS_PER_LINE:
        raise VwfCellCompileError(
            f"VWF line needs {len(cells)} cells; stock grid owns {VWF_CELLS_PER_LINE}"
        )

    tokens: list[int] = []
    for cell in cells:
        ids = tuple(mapping[c] - 0x80 for c in cell)
        descriptor = VwfCellDescriptor(ids, _cell_width(cell, font))
        tokens.append(dictionary.token(descriptor))

    return VwfCompiledLine(
        text=text,
        tokens=tuple(tokens),
        pixel_width=measure_text(text, font),
    )


def _compile_vwf_lines(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
    dictionary: VwfDictionaryBuilder,
) -> tuple[VwfCompiledLine, ...]:
    if font.characters != glyphs.characters:
        raise VwfCellCompileError(
            "VWF font and one-byte English glyph table must share character order"
        )
    lines = wrap_vwf_cells(text, font)
    return tuple(pack_vwf_line(line, font, glyphs, dictionary) for line in lines)


def compile_vwf_corpus(
    texts: tuple[str, ...],
    font: VwfFont,
    glyphs: EnglishGlyphTable,
) -> tuple[VwfCompiledText, ...]:
    """Compile one mission corpus against a single shared cell dictionary."""

    if not texts:
        return ()
    dictionary = VwfDictionaryBuilder()
    compiled_lines = tuple(
        _compile_vwf_lines(text, font, glyphs, dictionary) for text in texts
    )
    final_dictionary = dictionary.finish()
    return tuple(
        VwfCompiledText(lines, final_dictionary) for lines in compiled_lines
    )


def compile_vwf_text(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
) -> VwfCompiledText:
    """Compile one text using the same shared-dictionary machinery as missions."""

    return compile_vwf_corpus((text,), font, glyphs)[0]


def render_vwf_cell(
    descriptor: VwfCellDescriptor,
    font: VwfFont,
) -> bytes:
    """Pre-render one descriptor into the stock 32-byte 16x16 staging format."""

    rows = [0] * 16
    x = 0
    for glyph_id in descriptor.glyph_ids:
        if not 0 <= glyph_id < len(font.glyphs):
            raise VwfCellCompileError("VWF descriptor glyph ID is outside the font")
        glyph = font.glyphs[glyph_id]
        metric = font.metrics[glyph_id]
        if metric.width:
            for y, source in enumerate(glyph):
                for gx in range(metric.left, metric.right + 1):
                    if source & (0x80 >> gx):
                        px = x + gx - metric.left
                        if not 0 <= px < VWF_CELL_PIXELS:
                            raise VwfCellCompileError(
                                "VWF glyph writes outside its 16-pixel staged cell"
                            )
                        rows[y] |= 1 << (15 - px)
        x += metric.advance

    if x < descriptor.pixel_width or x > VWF_CELL_PIXELS + 1:
        raise VwfCellCompileError("VWF staged-cell advance is inconsistent")

    out = bytearray()
    for row in rows:
        out.extend(((row >> 8) & 0xFF, row & 0xFF))
    if len(out) != VWF_STAGED_CELL_BYTES:
        raise AssertionError("VWF staged cell has the wrong byte length")
    return bytes(out)


def render_vwf_dictionary(
    dictionary: VwfCellDictionary,
    font: VwfFont,
) -> bytes:
    """Render a mission dictionary as token-indexed 32-byte Card-RAM cells."""

    payload = b"".join(render_vwf_cell(item, font) for item in dictionary.descriptors)
    if len(payload) > VWF_CARD_RAM_BANK_COUNT * 0x2000:
        raise VwfCellCompileError("pre-rendered VWF dictionary exceeds reserved Card RAM")
    return payload


def normalized_vwf_atlas(font: VwfFont) -> tuple[bytes, ...]:
    """Return 8x16 glyph rows shifted left to their visible metric bound.

    Runtime VWF composition then needs only the glyph ID, current pixel X, and
    metric advance; it does not need to repeat left-bearing analysis.
    """

    rows: list[bytes] = []
    for glyph, metric in zip(font.glyphs, font.metrics, strict=True):
        if metric.width == 0:
            rows.append(bytes(16))
            continue
        shifted = bytes((row << metric.left) & 0xFF for row in glyph)
        rows.append(shifted)
    return tuple(rows)


def vwf_advance_table(font: VwfFont) -> bytes:
    if any(not 0 <= metric.advance <= 0xFF for metric in font.metrics):
        raise VwfCellCompileError("VWF advance does not fit one byte")
    return bytes(metric.advance for metric in font.metrics)


__all__ = [
    "MAX_CELL_GLYPHS",
    "VWF_CARD_RAM_BASE_BANK",
    "VWF_CARD_RAM_BANK_COUNT",
    "VWF_CELL_PIXELS",
    "VWF_CELLS_PER_LINE",
    "VWF_DESCRIPTOR_BYTES",
    "VWF_MODE_SIGNATURE",
    "VWF_SEGMENT_END_TOKEN",
    "VWF_STAGED_CELL_BYTES",
    "VWF_TOKEN_CAPACITY",
    "VWF_TOKEN_FIRST_MAX",
    "VWF_TOKEN_FIRST_MIN",
    "VwfCellCompileError",
    "VwfDictionaryBuilder",
    "VwfCellDescriptor",
    "VwfCellDictionary",
    "VwfCompiledLine",
    "VwfCompiledText",
    "compile_vwf_corpus",
    "compile_vwf_text",
    "decode_vwf_token",
    "encode_vwf_token",
    "normalized_vwf_atlas",
    "render_vwf_cell",
    "render_vwf_dictionary",
    "pack_vwf_line",
    "wrap_vwf_cells",
    "vwf_advance_table",
]
