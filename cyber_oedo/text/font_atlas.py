"""English 8x16 glyph-atlas helpers for the packed two-character renderer.

The runtime design keeps the PC Engine's existing 16x16 staging contract.
Each English display glyph is an 8x16 one-bit bitmap (16 row bytes). Two
English glyphs are interleaved row-by-row to form the 32-byte staging cell that
normally receives one 16x16 System Card glyph.

Font source files are intentionally external inputs. The repository owns the
rasterization rules and binary layout, not redistributed font binaries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

GLYPH_WIDTH = 8
GLYPH_HEIGHT = 16
GLYPH_BYTES = 16
PAIR_CELL_BYTES = 32


class FontAtlasError(ValueError):
    """Raised when an English bitmap glyph/atlas violates the runtime contract."""


@dataclass(frozen=True, slots=True)
class RasterConfig:
    """Deterministic raster parameters for a user-supplied TrueType/OpenType font."""

    point_size: int = 13
    threshold: int = 96
    x_shift: int = 0
    y_shift: int = 0

    def __post_init__(self) -> None:
        if self.point_size <= 0:
            raise FontAtlasError("point_size must be positive")
        if not 0 <= self.threshold <= 255:
            raise FontAtlasError("threshold must be in 0..255")


@dataclass(frozen=True, slots=True)
class RasterizedAtlas:
    """One-byte glyph IDs mapped to packed 8x16 one-bit bitmaps."""

    characters: str
    glyphs: tuple[bytes, ...]
    source_sha256: str
    config: RasterConfig

    def __post_init__(self) -> None:
        if len(self.characters) != len(self.glyphs):
            raise FontAtlasError("character and glyph counts differ")
        if len(set(self.characters)) != len(self.characters):
            raise FontAtlasError("atlas characters contain duplicates")
        for glyph in self.glyphs:
            validate_glyph(glyph)

    def glyph(self, glyph_id: int) -> bytes:
        if not 0 <= glyph_id < len(self.glyphs):
            raise FontAtlasError(f"glyph ID {glyph_id} is outside the atlas")
        return self.glyphs[glyph_id]

    def binary(self) -> bytes:
        return b"".join(self.glyphs)


def validate_glyph(glyph: bytes) -> None:
    """Require exactly one 8-pixel row byte for each of 16 rows."""

    if len(glyph) != GLYPH_BYTES:
        raise FontAtlasError(
            f"8x16 glyph must be {GLYPH_BYTES} bytes, got {len(glyph)}"
        )


def compose_pair_cell(left: bytes, right: bytes) -> bytes:
    """Compose two 8x16 glyphs into the stock 32-byte 16x16 staging cell.

    The System Card 16x16 font staging buffer is sixteen rows by two bytes.
    The first byte is the left eight pixels and the second byte the right eight
    pixels. This routine preserves that row-major contract exactly.
    """

    validate_glyph(left)
    validate_glyph(right)
    cell = bytearray()
    for left_row, right_row in zip(left, right, strict=True):
        cell.append(left_row)
        cell.append(right_row)
    return bytes(cell)


def split_pair_cell(cell: bytes) -> tuple[bytes, bytes]:
    """Inverse of :func:`compose_pair_cell` for diagnostics/tests."""

    if len(cell) != PAIR_CELL_BYTES:
        raise FontAtlasError(
            f"16x16 pair cell must be {PAIR_CELL_BYTES} bytes, got {len(cell)}"
        )
    return bytes(cell[0::2]), bytes(cell[1::2])


def _pack_image_rows(image) -> bytes:
    """Pack an 8x16 1-bit Pillow image into one byte per scanline."""

    if image.size != (GLYPH_WIDTH, GLYPH_HEIGHT):
        raise FontAtlasError(
            f"glyph image must be {GLYPH_WIDTH}x{GLYPH_HEIGHT}, got {image.size}"
        )
    rows = bytearray()
    pixels = image.load()
    for y in range(GLYPH_HEIGHT):
        value = 0
        for x in range(GLYPH_WIDTH):
            if pixels[x, y]:
                value |= 0x80 >> x
        rows.append(value)
    return bytes(rows)


def rasterize_character(
    font_path: str | Path,
    character: str,
    *,
    config: RasterConfig = RasterConfig(),
) -> bytes:
    """Rasterize one character into the deterministic 8x16 one-bit contract.

    Pillow is an optional graphics dependency and is imported only when this
    function is used. Glyphs are centered from their measured bounding box and
    then thresholded to one bit.
    """

    if len(character) != 1:
        raise FontAtlasError("rasterize_character requires exactly one character")

    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Pillow is required for TrueType/OpenType font rasterization"
        ) from error

    font_path = Path(font_path)
    if not font_path.is_file():
        raise FileNotFoundError(font_path)

    font = ImageFont.truetype(str(font_path), config.point_size)
    gray = Image.new("L", (GLYPH_WIDTH, GLYPH_HEIGHT), 0)
    if character != " ":
        draw = ImageDraw.Draw(gray)
        bbox = draw.textbbox((0, 0), character, font=font)
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        x = (GLYPH_WIDTH - width) // 2 - bbox[0] + config.x_shift
        y = (GLYPH_HEIGHT - height) // 2 - bbox[1] + config.y_shift
        draw.text((x, y), character, font=font, fill=255)

    mono = gray.point(lambda value: 255 if value >= config.threshold else 0, mode="1")
    return _pack_image_rows(mono)


def rasterize_atlas(
    font_path: str | Path,
    characters: str,
    *,
    config: RasterConfig = RasterConfig(),
) -> RasterizedAtlas:
    """Rasterize an ordered unique character repertoire."""

    if len(set(characters)) != len(characters):
        raise FontAtlasError("atlas character list contains duplicates")
    font_path = Path(font_path)
    source_hash = hashlib.sha256(font_path.read_bytes()).hexdigest()
    glyphs = tuple(
        rasterize_character(font_path, character, config=config)
        for character in characters
    )
    return RasterizedAtlas(
        characters=characters,
        glyphs=glyphs,
        source_sha256=source_hash,
        config=config,
    )


def compose_pair_from_atlas(
    atlas: RasterizedAtlas,
    left_id: int,
    right_id: int,
) -> bytes:
    """Build the exact $4C6C-style staging bytes for a packed English pair."""

    return compose_pair_cell(atlas.glyph(left_id), atlas.glyph(right_id))
