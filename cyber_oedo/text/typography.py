"""Build-time typography contracts for the future self-contained English engine.

This module does not patch the game or claim runtime storage. It defines the
font repertoire and pixel-layout rules that renderer assets must satisfy once a
loader/RAM location has been proven by B3 runtime evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


PRINTABLE_ASCII = "".join(chr(codepoint) for codepoint in range(0x20, 0x7F))
CORPUS_TYPOGRAPHY_EXTENSIONS = "¥–—‘’“”■"
PRODUCTION_REPERTOIRE = PRINTABLE_ASCII + CORPUS_TYPOGRAPHY_EXTENSIONS
FONT_HEIGHT = 16
MAX_GLYPH_WIDTH = 8


@dataclass(frozen=True, slots=True)
class GlyphMetric:
    """Describe one stored 8-pixel-wide glyph and its proportional advance."""

    character: str
    advance: int

    def __post_init__(self) -> None:
        if len(self.character) != 1:
            raise ValueError("glyph metric must describe exactly one character")
        if not 1 <= self.advance <= MAX_GLYPH_WIDTH:
            raise ValueError("glyph advance must lie between 1 and 8 pixels")


@dataclass(frozen=True, slots=True)
class FontMetrics:
    """Provide strict character coverage and pixel measurement for one font."""

    name: str
    role: str
    glyphs: tuple[GlyphMetric, ...]
    line_height: int = FONT_HEIGHT
    _advances: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("font name must not be empty")
        if not self.role:
            raise ValueError("font role must not be empty")
        if self.line_height <= 0:
            raise ValueError("line height must be positive")
        characters = [glyph.character for glyph in self.glyphs]
        if not characters:
            raise ValueError("font must contain at least one glyph")
        if len(characters) != len(set(characters)):
            raise ValueError("font glyph characters must be unique")
        object.__setattr__(
            self,
            "_advances",
            MappingProxyType({glyph.character: glyph.advance for glyph in self.glyphs}),
        )

    @classmethod
    def fixed_width(
        cls,
        name: str,
        role: str,
        repertoire: str = PRODUCTION_REPERTOIRE,
        *,
        advance: int = MAX_GLYPH_WIDTH,
    ) -> "FontMetrics":
        """Build deterministic fixed-width metrics for a stored repertoire."""

        if len(repertoire) != len(set(repertoire)):
            raise ValueError("font repertoire must not contain duplicates")
        return cls(
            name=name,
            role=role,
            glyphs=tuple(GlyphMetric(character, advance) for character in repertoire),
        )

    def advance_for(self, character: str) -> int:
        """Return one glyph advance, rejecting characters absent from the font."""

        if len(character) != 1:
            raise ValueError("advance lookup requires exactly one character")
        try:
            return self._advances[character]
        except KeyError as error:
            raise ValueError(
                f"font {self.name!r} does not contain {character!r}"
            ) from error

    def measure(self, text: str) -> int:
        """Return the exact horizontal advance of *text* in pixels."""

        return sum(self.advance_for(character) for character in text)

    @property
    def repertoire(self) -> str:
        """Return glyph characters in deterministic storage order."""

        return "".join(glyph.character for glyph in self.glyphs)


@dataclass(frozen=True, slots=True)
class PixelGeometry:
    """Describe one renderer window in pixels rather than character cells."""

    width_pixels: int
    maximum_lines: int

    def __post_init__(self) -> None:
        if self.width_pixels <= 0:
            raise ValueError("pixel width must be positive")
        if self.maximum_lines <= 0:
            raise ValueError("maximum lines must be positive")


def wrap_text_pixels(
    text: str,
    metrics: FontMetrics,
    geometry: PixelGeometry,
) -> tuple[str, ...]:
    """Wrap single-spaced English by glyph advances without splitting words."""

    words = text.split(" ")
    if not text or text.strip() != text or any(not word for word in words):
        raise ValueError("text must use single spaces without outer whitespace")
    for character in text:
        metrics.advance_for(character)
    for word in words:
        if metrics.measure(word) > geometry.width_pixels:
            raise ValueError(
                f"word exceeds {geometry.width_pixels}-pixel line: {word!r}"
            )

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if metrics.measure(candidate) <= geometry.width_pixels:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    if len(lines) > geometry.maximum_lines:
        raise ValueError("wrapped text exceeds the available line count")
    return tuple(lines)


def packed_font_bytes(
    glyph_count: int,
    *,
    glyph_height: int = FONT_HEIGHT,
    bytes_per_row: int = 1,
) -> int:
    """Return packed bitmap bytes for fixed-height row-major glyph storage."""

    if glyph_count <= 0:
        raise ValueError("glyph count must be positive")
    if glyph_height <= 0:
        raise ValueError("glyph height must be positive")
    if bytes_per_row <= 0:
        raise ValueError("bytes per row must be positive")
    return glyph_count * glyph_height * bytes_per_row


__all__ = [
    "CORPUS_TYPOGRAPHY_EXTENSIONS",
    "FONT_HEIGHT",
    "FontMetrics",
    "GlyphMetric",
    "MAX_GLYPH_WIDTH",
    "PRINTABLE_ASCII",
    "PRODUCTION_REPERTOIRE",
    "PixelGeometry",
    "packed_font_bytes",
    "wrap_text_pixels",
]
