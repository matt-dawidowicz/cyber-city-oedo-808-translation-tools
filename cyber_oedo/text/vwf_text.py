"""Build-time proportional English renderer assets for the PC Engine dialogue box."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

LINE_PIXELS = 176
GLYPH_HEIGHT = 16
TILE_WIDTH = 8
TILE_HEIGHT = 8
TILES_PER_LINE = LINE_PIXELS // TILE_WIDTH
LINE_TILE_BYTES_4BPP = TILES_PER_LINE * 2 * 32
DEFAULT_SPACE_ADVANCE = 4
DEFAULT_TRACKING = 1


class VwfTextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GlyphMetric:
    character: str
    left: int
    right: int
    width: int
    advance: int


@dataclass(frozen=True, slots=True)
class VwfFont:
    characters: str
    glyphs: tuple[bytes, ...]
    metrics: tuple[GlyphMetric, ...]

    def __post_init__(self) -> None:
        if len(self.characters) != len(self.glyphs) or len(self.glyphs) != len(self.metrics):
            raise VwfTextError("character/glyph/metric counts differ")
        if len(set(self.characters)) != len(self.characters):
            raise VwfTextError("characters must be unique")
        for glyph in self.glyphs:
            if len(glyph) != GLYPH_HEIGHT:
                raise VwfTextError("glyph must contain 16 one-byte scanlines")

    def index(self, character: str) -> int:
        try:
            return self.characters.index(character)
        except ValueError as error:
            raise VwfTextError(f"character {character!r} is not in the font") from error

    def glyph(self, character: str) -> bytes:
        return self.glyphs[self.index(character)]

    def metric(self, character: str) -> GlyphMetric:
        return self.metrics[self.index(character)]


@dataclass(frozen=True, slots=True)
class VwfLine:
    text: str
    pixel_width: int
    bitmap_rows: tuple[int, ...]
    tile_bytes_4bpp: bytes
    character_end_pixels: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.bitmap_rows) != GLYPH_HEIGHT:
            raise VwfTextError("line bitmap must contain 16 rows")
        if len(self.tile_bytes_4bpp) != LINE_TILE_BYTES_4BPP:
            raise VwfTextError("line tile payload has the wrong size")
        if len(self.character_end_pixels) != len(self.text):
            raise VwfTextError("character reveal map length differs from text")


@dataclass(frozen=True, slots=True)
class VwfPage:
    lines: tuple[VwfLine, ...]

    def __post_init__(self) -> None:
        if not 1 <= len(self.lines) <= 3:
            raise VwfTextError("a dialogue page must contain one to three lines")

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def tile_bytes_4bpp(self) -> bytes:
        return b"".join(line.tile_bytes_4bpp for line in self.lines)


def _column_bounds(glyph: bytes) -> tuple[int, int] | None:
    used = 0
    for row in glyph:
        used |= row
    if used == 0:
        return None
    left = next(x for x in range(8) if used & (0x80 >> x))
    right = max(x for x in range(8) if used & (0x80 >> x))
    return left, right


def derive_vwf_font(
    characters: str,
    glyphs: Iterable[bytes],
    *,
    tracking: int = DEFAULT_TRACKING,
    space_advance: int = DEFAULT_SPACE_ADVANCE,
) -> VwfFont:
    glyph_tuple = tuple(glyphs)
    if len(characters) != len(glyph_tuple):
        raise VwfTextError("character/glyph counts differ")
    if tracking < 0:
        raise VwfTextError("tracking must be non-negative")
    if space_advance <= 0:
        raise VwfTextError("space advance must be positive")
    metrics: list[GlyphMetric] = []
    for character, glyph in zip(characters, glyph_tuple, strict=True):
        if len(glyph) != GLYPH_HEIGHT:
            raise VwfTextError("glyph must contain 16 scanlines")
        bounds = _column_bounds(glyph)
        if character == " " or bounds is None:
            metrics.append(GlyphMetric(character, 0, -1, 0, space_advance))
            continue
        left, right = bounds
        width = right - left + 1
        metrics.append(GlyphMetric(character, left, right, width, width + tracking))
    return VwfFont(characters, glyph_tuple, tuple(metrics))


def measure_text(text: str, font: VwfFont) -> int:
    if not text:
        return 0
    advances = [font.metric(character).advance for character in text]
    final = font.metric(text[-1])
    trailing_tracking = max(0, final.advance - final.width) if final.width else 0
    return sum(advances) - trailing_tracking


def wrap_vwf(text: str, font: VwfFont, *, max_pixels: int = LINE_PIXELS) -> tuple[str, ...]:
    if max_pixels <= 0:
        raise VwfTextError("max_pixels must be positive")
    if max_pixels > LINE_PIXELS:
        raise VwfTextError(
            f"max_pixels cannot exceed the fixed {LINE_PIXELS}px dialogue canvas"
        )
    if not text or text.strip() != text or "  " in text:
        raise VwfTextError("text must use single spaces without outer whitespace")
    words = text.split(" ")
    for word in words:
        if measure_text(word, font) > max_pixels:
            raise VwfTextError(f"word exceeds {max_pixels}px line: {word!r}")
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = current + " " + word
        if measure_text(candidate, font) <= max_pixels:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def _blit_glyph(rows: list[int], glyph: bytes, metric: GlyphMetric, x: int) -> None:
    if metric.width == 0:
        return
    for y, source in enumerate(glyph):
        for gx in range(metric.left, metric.right + 1):
            if source & (0x80 >> gx):
                px = x + gx - metric.left
                if not 0 <= px < LINE_PIXELS:
                    raise VwfTextError("glyph writes outside the line bitmap")
                rows[y] |= 1 << (LINE_PIXELS - 1 - px)


def _line_rows(text: str, font: VwfFont) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    rows = [0] * GLYPH_HEIGHT
    x = 0
    ends: list[int] = []
    for index, character in enumerate(text):
        glyph = font.glyph(character)
        metric = font.metric(character)
        _blit_glyph(rows, glyph, metric, x)
        is_last = index == len(text) - 1
        advance = metric.advance
        if is_last and metric.width:
            advance = metric.width
        x += advance
        if x > LINE_PIXELS:
            raise VwfTextError(f"line exceeds {LINE_PIXELS}px")
        ends.append(x)
    return tuple(rows), tuple(ends), x


def _tile_4bpp(rows: tuple[int, ...], tile_x: int, tile_y: int) -> bytes:
    first = bytearray()
    second = bytearray()
    for local_y in range(8):
        y = tile_y * 8 + local_y
        shift = LINE_PIXELS - 8 - tile_x * 8
        bits = (rows[y] >> shift) & 0xFF
        first.extend((bits, 0x00))
        second.extend((0x00, 0x00))
    return bytes(first + second)


def line_to_tiles_4bpp(rows: tuple[int, ...]) -> bytes:
    if len(rows) != GLYPH_HEIGHT:
        raise VwfTextError("line bitmap must contain 16 rows")
    out = bytearray()
    for tile_y in range(2):
        for tile_x in range(TILES_PER_LINE):
            out.extend(_tile_4bpp(rows, tile_x, tile_y))
    return bytes(out)


def render_line(text: str, font: VwfFont) -> VwfLine:
    rows, ends, width = _line_rows(text, font)
    return VwfLine(text, width, rows, line_to_tiles_4bpp(rows), ends)


def paginate_vwf(
    text: str,
    font: VwfFont,
    *,
    max_pixels: int = LINE_PIXELS,
    rows_per_page: int = 3,
) -> tuple[VwfPage, ...]:
    if rows_per_page <= 0:
        raise VwfTextError("rows_per_page must be positive")
    lines = wrap_vwf(text, font, max_pixels=max_pixels)
    pages: list[VwfPage] = []
    for start in range(0, len(lines), rows_per_page):
        pages.append(VwfPage(tuple(render_line(line, font) for line in lines[start:start + rows_per_page])))
    return tuple(pages)


def character_delta_tiles(line: VwfLine) -> tuple[tuple[int, ...], ...]:
    """Return tile columns that must be refreshed after each character reveal."""
    previous = 0
    result: list[tuple[int, ...]] = []
    for end in line.character_end_pixels:
        if end <= previous:
            result.append(())
        else:
            first = previous // TILE_WIDTH
            last = max(first, (end - 1) // TILE_WIDTH)
            result.append(tuple(range(first, last + 1)))
        previous = end
    return tuple(result)
