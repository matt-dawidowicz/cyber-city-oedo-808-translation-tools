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
        if len(self.descriptors) >= VWF_SEGMENT_END_TOKEN:
            raise VwfCellCompileError("VWF dictionary exceeds 16-bit token space")

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
                out.extend(token.to_bytes(2, "little"))
            out.extend(VWF_SEGMENT_END_TOKEN.to_bytes(2, "little"))
            if line_index < len(self.lines) - 1:
                out.append(0x40)
        return bytes(out)


class _DictionaryBuilder:
    def __init__(self) -> None:
        self._rows: list[VwfCellDescriptor] = []
        self._by_glyphs: dict[tuple[int, ...], int] = {}

    def token(self, descriptor: VwfCellDescriptor) -> int:
        key = descriptor.glyph_ids
        existing = self._by_glyphs.get(key)
        if existing is not None:
            return existing
        token = len(self._rows)
        if token == VWF_SEGMENT_END_TOKEN:
            raise VwfCellCompileError("VWF token space exhausted")
        self._rows.append(descriptor)
        self._by_glyphs[key] = token
        return token

    def finish(self) -> VwfCellDictionary:
        return VwfCellDictionary(tuple(self._rows))


def _cell_width(text: str, font: VwfFont) -> int:
    return measure_text(text, font)


def pack_vwf_line(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
    dictionary: _DictionaryBuilder,
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
            # A space that would become the final pixel(s) of a cell is allowed
            # to fall on the cell boundary rather than creating a blank-leading
            # next cell.
            cells.append(current.rstrip() or current)
            current = character.lstrip()
            if not current:
                continue
        else:
            current = candidate

        if _cell_width(current, font) > VWF_CELL_PIXELS:
            raise VwfCellCompileError(
                f"single VWF glyph/cluster exceeds {VWF_CELL_PIXELS}px: {current!r}"
            )

    if current:
        cells.append(current.rstrip() or current)

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


def compile_vwf_text(
    text: str,
    font: VwfFont,
    glyphs: EnglishGlyphTable,
) -> VwfCompiledText:
    """Wrap by pixels, pack into stock cells, and deduplicate cell descriptors."""

    if font.characters != glyphs.characters:
        raise VwfCellCompileError(
            "VWF font and one-byte English glyph table must share character order"
        )
    lines = wrap_vwf(text, font, max_pixels=LINE_PIXELS)
    dictionary = _DictionaryBuilder()
    compiled = tuple(pack_vwf_line(line, font, glyphs, dictionary) for line in lines)
    return VwfCompiledText(compiled, dictionary.finish())


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
    "VwfCellCompileError",
    "VwfCellDescriptor",
    "VwfCellDictionary",
    "VwfCompiledLine",
    "VwfCompiledText",
    "compile_vwf_text",
    "normalized_vwf_atlas",
    "pack_vwf_line",
    "vwf_advance_table",
]
