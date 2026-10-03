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
VWF_TOKEN_FIRST_MAX = 0x1F
VWF_TOKEN_CAPACITY = (VWF_TOKEN_FIRST_MAX - VWF_TOKEN_FIRST_MIN + 1) * 0x100
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


def pack_vwf_line(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
    dictionary: VwfDictionaryBuilder,
) -> VwfCompiledLine:
    """Pack one already-wrapped line into <=11 proportional 16-pixel cells."""

    if not text:
        raise VwfCellCompileError("VWF line must not be empty")
    mapping = glyphs.char_to_byte
    cells: list[str] = []
    current = ""

    for character in text:
        if character not in mapping:
            raise VwfCellCompileError(f"character {character!r} is absent from glyph table")
        candidate = current + character
        if (
            current
            and (
                len(candidate) > MAX_CELL_GLYPHS
                or _cell_width(candidate, font) > VWF_CELL_PIXELS
            )
        ):
            # Preserve the exact visible character stream. If the character
            # that overflows is a space, carry that space into the next cell;
            # dropping it can visually concatenate adjacent words when the
            # preceding cell is full.
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
    lines = wrap_vwf(text, font, max_pixels=LINE_PIXELS)
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
    "VWF_CELL_PIXELS",
    "VWF_CELLS_PER_LINE",
    "VWF_DESCRIPTOR_BYTES",
    "VWF_MODE_SIGNATURE",
    "VWF_SEGMENT_END_TOKEN",
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
    "pack_vwf_line",
    "vwf_advance_table",
]
