#!/usr/bin/env python3
"""Generate the optional reference-matched opening-title graphic.

The game's first visible screen is a 256-by-240 image stored as 960
consecutive PC Engine 8-by-8, four-bit planar tiles. The default replacement
uses a packed four-bit coverage mask derived from the approved user-supplied
logo reference. It therefore preserves the reference's exact composition,
letterforms, and antialiased edges instead of approximating them with a
bundled font.

The packed mask is original replacement artwork, not extracted game content.
It expands with only Python's standard library and preserves four-bit
luminance coverage from the approved master. A generated grayscale replacement
for the original seven-frame title palette makes those intermediate indexes
stable at runtime instead of allowing the old color cycle to tint the edges.
The optional ``--source-image`` CLI path uses Pillow only when contributors
deliberately import another master image. The disc builder never requires
Pillow.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import pathlib
import zlib
from collections.abc import Sequence

from cyber_oedo.graphics.pce_graphics import encode_tile
from cyber_oedo.graphics.title_logo_mask import (
    LOGO_MASK_B85,
    LOGO_MASK_BITS_PER_PIXEL,
    LOGO_MASK_HEIGHT,
    LOGO_MASK_PACKED_BYTES,
    LOGO_MASK_PACKED_SHA256,
    LOGO_MASK_WIDTH,
)


SCREEN_WIDTH = 256
SCREEN_HEIGHT = 240
TILE_WIDTH = 8
TILE_HEIGHT = 8
TILES_WIDE = SCREEN_WIDTH // TILE_WIDTH
TILES_HIGH = SCREEN_HEIGHT // TILE_HEIGHT
TITLE_ASSET_BYTES = TILES_WIDE * TILES_HIGH * 32
BACKGROUND_INDEX = 0
TITLE_PALETTE_COLORS = 16
TITLE_PALETTE_FRAMES = 7
TITLE_PALETTE_BYTES = TITLE_PALETTE_COLORS * TITLE_PALETTE_FRAMES * 2
LUMINANCE_BLACK_POINT = 8
LUMINANCE_WHITE_POINT = 200
TITLE_SUBTITLE = "ATTRIBUTE OF THE BEAST"
TITLE_FIRST_VISIBLE_INDEX = 6
TITLE_COVERAGE_TO_PALETTE = (
    0,
    0,
    6,
    7,
    8,
    8,
    9,
    10,
    11,
    11,
    12,
    13,
    14,
    14,
    15,
    15,
)
TITLE_PALETTE_LEVELS = (
    0,
    0,
    0,
    0,
    0,
    0,
    1,
    1,
    2,
    3,
    3,
    4,
    5,
    5,
    6,
    7,
)


def decode_embedded_logo_mask() -> list[int]:
    """Expand the approved packed logo mask into palette indexes.

    Returns:
        Exactly 61,440 row-major palette indexes from 0 through 15. Each
        packed byte contributes its high nibble and then its low nibble.

    Raises:
        ValueError: If Base85 or zlib decoding fails, the packed size differs
            from 30,720 bytes, its SHA-256 does not match the reviewed mask,
            or its declared packing is incompatible.

    Design Decisions:
        The four-bit coverage map retains Lanczos antialiasing without
        embedding a PNG or requiring Pillow during ordinary builds.
        Independent size and digest checks turn accidental edits into
        explicit failures.
    """

    try:
        packed = zlib.decompress(base64.b85decode(LOGO_MASK_B85))
    except (ValueError, zlib.error) as error:
        raise ValueError("embedded title-logo mask is invalid") from error
    if len(packed) != LOGO_MASK_PACKED_BYTES:
        raise ValueError("embedded title-logo mask has the wrong packed size")
    digest = hashlib.sha256(packed).hexdigest()
    if digest != LOGO_MASK_PACKED_SHA256:
        raise ValueError("embedded title-logo mask failed its SHA-256 guard")
    if LOGO_MASK_WIDTH != SCREEN_WIDTH or LOGO_MASK_HEIGHT != SCREEN_HEIGHT:
        raise ValueError("embedded title-logo dimensions are incompatible")
    if LOGO_MASK_BITS_PER_PIXEL != 4:
        raise ValueError("embedded title-logo packing is incompatible")

    pixels: list[int] = []
    for byte in packed:
        pixels.extend((byte >> 4, byte & 0x0F))
    if len(pixels) != SCREEN_WIDTH * SCREEN_HEIGHT:
        raise AssertionError("decoded title mask has an invalid pixel count")
    return pixels


def build_title_pixels_from_image(
    image_path: pathlib.Path,
) -> list[int]:
    """Convert an arbitrary master image to the title's four-bit frame.

    Args:
        image_path: Source image readable by Pillow.

    Returns:
        Exactly 61,440 row-major hardware palette indexes. The source is
        proportionally fitted inside 256 by 240, centered on a black frame,
        quantized to four-bit coverage, and remapped away from the low indexes
        reserved for suppressing the game's top-border artifacts.

    Raises:
        ModuleNotFoundError: If Pillow is unavailable.
        OSError: If Pillow cannot open or decode the source image.
        ValueError: If the source dimensions or resulting frame is invalid or
            contains no foreground/background contrast.

    Side Effects:
        Opens and reads ``image_path`` without modifying it.

    Design Decisions:
        Proportional Lanczos reduction matches the approved 1448-by-1086
        reference conversion: 256 by 192, centered with 24 black rows above
        and below. Values at or below 8 become black and values at or above
        200 become white; the range between them retains four-bit edge
        coverage. Those points keep the pale master lettering solid on the
        eight-level hardware palette while materially improving curves and
        diagonals. The disc builder pairs this asset with a generated
        grayscale title-palette replacement.
    """

    try:
        from PIL import Image
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "Pillow is required only for --source-image conversion"
        ) from error

    with Image.open(image_path) as source:
        grayscale = source.convert("L")
    if grayscale.width <= 0 or grayscale.height <= 0:
        raise ValueError("source image dimensions must be positive")

    scale = min(
        SCREEN_WIDTH / grayscale.width,
        SCREEN_HEIGHT / grayscale.height,
    )
    width = max(1, round(grayscale.width * scale))
    height = max(1, round(grayscale.height * scale))
    resized = grayscale.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )
    left = (SCREEN_WIDTH - width) // 2
    top = (SCREEN_HEIGHT - height) // 2
    pixels = [BACKGROUND_INDEX] * (SCREEN_WIDTH * SCREEN_HEIGHT)
    luminance = resized.tobytes()
    for y in range(height):
        for x in range(width):
            value = luminance[y * width + x]
            coverage = quantize_title_luminance(value)
            pixels[(top + y) * SCREEN_WIDTH + left + x] = title_palette_index(coverage)

    if not any(pixels):
        raise ValueError("source image produced no title foreground")
    if all(pixel == 15 for pixel in pixels):
        raise ValueError("source image produced no title background")
    return pixels


def quantize_title_luminance(value: int) -> int:
    """Map one 8-bit source luminance to a four-bit coverage index.

    Args:
        value: Integer luminance from 0 through 255.

    Returns:
        Palette index 0 through 15 using the reviewed black and white points.

    Raises:
        ValueError: If ``value`` is not an integer in the 8-bit range.

    Design Decisions:
        The approved master uses pale gray-purple lettering whose solid
        interiors peak below 255. Mapping 200 to index 15 prevents those
        interiors from appearing dull gray, while the linear interval above
        black point 8 retains the subpixel coverage that smooths edges.
    """

    if not isinstance(value, int) or not 0 <= value <= 255:
        raise ValueError("title luminance must be an integer from 0 to 255")
    if value <= LUMINANCE_BLACK_POINT:
        return 0
    if value >= LUMINANCE_WHITE_POINT:
        return 15
    span = LUMINANCE_WHITE_POINT - LUMINANCE_BLACK_POINT
    adjusted = value - LUMINANCE_BLACK_POINT
    return (adjusted * 15 + span // 2) // span


def title_palette_index(coverage: int) -> int:
    """Map one coverage value to an artifact-safe hardware palette index.

    Args:
        coverage: Four-bit luminance coverage from 0 through 15.

    Returns:
        Palette index 0 or 6 through 15. The mapping retains the same eight
        visible gray levels as the original clean-title palette.

    Raises:
        ValueError: If ``coverage`` is not an integer in the four-bit range.

    Design Decisions:
        The original title routine leaves a few low-index pixels active in the
        upper overscan area. A grayscale palette made indexes 2 through 5
        visible as stray gray dashes. Reserving indexes 0 through 5 as black
        suppresses those pixels. Remapping logo coverage into indexes 6
        through 15 preserves its antialiased luminance levels without changing
        the game's animation code or timing.
    """

    if not isinstance(coverage, int) or not 0 <= coverage <= 15:
        raise ValueError("title coverage must be an integer from 0 to 15")
    return TITLE_COVERAGE_TO_PALETTE[coverage]


def build_grayscale_title_palette_cycle() -> bytes:
    """Return seven identical artifact-safe grayscale title palettes.

    Returns:
        Exactly 224 bytes containing seven PC Engine palettes. Each little-
        endian 9-bit color word has equal three-bit red, green, and blue
        components. Indexes 0 through 5 are black; indexes 6 through 15 carry
        the hardware's seven visible gray levels.

    Design Decisions:
        The original title rotates seven colored palettes over the same tile
        indexes. Replacing every frame prevents antialiased edge indexes from
        shimmering or changing hue while preserving the existing animation
        code and timing. Keeping the first six indexes black also hides the
        original routine's stray upper-border pixels. The separate portrait
        palette immediately before this table is intentionally untouched.
    """

    words = tuple(level * 0x49 for level in TITLE_PALETTE_LEVELS)
    frame = b"".join(word.to_bytes(2, "little") for word in words)
    palette_cycle = frame * TITLE_PALETTE_FRAMES
    if len(palette_cycle) != TITLE_PALETTE_BYTES:
        raise AssertionError("generated title palette has an invalid size")
    return palette_cycle


def encode_title_pixels(pixels: Sequence[int]) -> bytes:
    """Encode one complete row-major title frame in tile-major order.

    Args:
        pixels: Exactly 61,440 palette indexes from 0 through 15.

    Returns:
        Exactly 30,720 bytes: 32 tiles per row, 30 rows, and 32 bytes per
        four-bit tile.

    Raises:
        ValueError: If the frame size or any palette index is invalid.

    Design Decisions:
        The boot program transfers this block as a complete ready-to-display
        image. Emitting tiles in screen order avoids tile deduplication,
        tilemap changes, and boot-code modifications.
    """

    if len(pixels) != SCREEN_WIDTH * SCREEN_HEIGHT:
        raise ValueError("title frame must contain exactly 61,440 pixels")
    if any(not isinstance(pixel, int) or not 0 <= pixel <= 15 for pixel in pixels):
        raise ValueError("title pixels must be palette indexes 0-15")

    encoded = bytearray()
    for tile_y in range(TILES_HIGH):
        for tile_x in range(TILES_WIDE):
            tile: list[int] = []
            for pixel_y in range(TILE_HEIGHT):
                row = (tile_y * TILE_HEIGHT + pixel_y) * SCREEN_WIDTH
                start = row + tile_x * TILE_WIDTH
                tile.extend(pixels[start : start + TILE_WIDTH])
            encoded.extend(encode_tile(tile))
    if len(encoded) != TITLE_ASSET_BYTES:
        raise AssertionError("generated title asset has an invalid size")
    return bytes(encoded)


def build_clean_title_pixels() -> list[int]:
    """Return the approved reference-matched title palette indexes.

    Returns:
        The exact 256-by-240 silhouette stored in ``title_logo_mask.py``,
        remapped to the artifact-safe hardware palette indexes.

    Notes:
        The historical function name remains stable for downstream patch
        projects. ``clean`` identifies the optional replacement variant, not a
        claim that its artwork is generic or independently redrawn.
    """

    return [title_palette_index(coverage) for coverage in decode_embedded_logo_mask()]


def build_clean_title_asset() -> bytes:
    """Return the approved title in the game's planar tile format.

    Returns:
        Exactly 30,720 bytes generated from the guarded embedded mask.

    Failure Conditions:
        Mask decoding, pixel validation, or tile encoding failures propagate.
    """

    return encode_title_pixels(build_clean_title_pixels())


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone title-asset generator parser.

    Returns:
        Parser supporting the approved embedded logo and optional master-image
        conversion for contributor revisions.
    """

    return argparse.ArgumentParser(
        description=("Generate the optional 256x240 PC Engine title graphic."),
    )


def main() -> None:
    """Generate a standalone title asset for inspection or modification.

    Inputs:
        Parses an output path and optional source-image path. Without
        ``--source-image``, uses the guarded approved logo coverage mask.

    Outputs:
        Writes the deterministic 30,720-byte tile block and prints its path.

    Side Effects:
        Optionally reads a master image, creates the output parent directory,
        and replaces the output file.

    Failure Conditions:
        ``argparse`` handles syntax errors. Image, validation, and file-system
        failures propagate without modifying a disc image.
    """

    parser = build_parser()
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination for the generated raw tile block",
    )
    parser.add_argument(
        "--source-image",
        type=pathlib.Path,
        help=(
            "optional image to fit, center, and threshold instead of using "
            "the approved embedded logo"
        ),
    )
    args = parser.parse_args()

    if args.source_image is None:
        pixels = build_clean_title_pixels()
    else:
        try:
            pixels = build_title_pixels_from_image(args.source_image)
        except (ModuleNotFoundError, OSError, ValueError) as error:
            parser.error(str(error))
    asset = encode_title_pixels(pixels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(asset)
    print(args.output)


if __name__ == "__main__":
    main()
