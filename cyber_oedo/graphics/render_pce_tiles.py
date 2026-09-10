#!/usr/bin/env python3
"""Render candidate PC Engine 4bpp tiles for visual reverse engineering.

The PC Engine stores one 8x8, 4-bits-per-pixel tile in 32 bytes. Bitplanes 0
and 1 occupy the first 16 bytes; bitplanes 2 and 3 occupy the next 16. This
tool decodes that layout from any byte offset in the extracted Track 2 payload.

The output uses a synthetic 16-step grayscale palette because palette RAM is
not reconstructed here. Correct shapes with wrong colors are still useful for
locating fonts, UI tiles, and graphics banks. A noisy image can simply mean
the selected offset does not contain raw tile data.

The command requires Pillow, reads only the requested payload range, creates
the output directory, and replaces the requested PNG. It does not decode
tilemaps, palettes, compression, or runtime VRAM placement.
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image


from cyber_oedo.graphics.pce_graphics import decode_tile


def grayscale_palette() -> list[int]:
    """Build a diagnostic grayscale palette for Pillow ``P`` images.

    Returns:
        A 768-integer RGB palette. Entries 0-15 form evenly spaced grayscale
        values; unused entries 16-255 are black.

    Notes:
        Palette values visualize indexes only. They are not colors recovered
        from the game or emulated palette RAM.
    """

    palette: list[int] = []
    for value in range(16):
        shade = round(value * 255 / 15)
        palette.extend((shade, shade, shade))
    palette.extend([0] * (768 - len(palette)))
    return palette


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser explaining payload-relative offsets and diagnostic rendering.
        Paths, dimensions, and scale arguments are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Render raw 32-byte PC Engine 4bpp tiles from an arbitrary "
            "payload offset using a diagnostic grayscale palette."
        ),
        epilog=(
            "Offsets accept decimal or 0x-prefixed hexadecimal. They address "
            "the extracted 2048-byte Track 2 payload."
        ),
    )


def main() -> None:
    """Render candidate 4bpp tiles from an arbitrary payload offset.

    Inputs:
        Parses payload and PNG paths, payload offset, maximum tile count, tiles
        per row, and integer scale from command-line arguments.

    Outputs:
        Writes one indexed-color PNG containing every complete tile read.
        Normal success produces no console output.

    Side Effects:
        Reads up to ``tiles * 32`` bytes, creates the output parent directory,
        and replaces the destination PNG.

    Failure Conditions:
        ``argparse`` exits for negative offsets, non-positive dimensions or
        scale, or an offset with no complete tile. File-system and Pillow
        encoding errors propagate.

    Design Decisions:
        Incomplete bytes at the end of the selected range are ignored.
        Nearest-neighbor scaling preserves hard pixel edges, and a requested
        row wider than the tile count intentionally leaves blank image space.
    """

    parser = build_parser()
    parser.add_argument(
        "input",
        type=pathlib.Path,
        help="Track 2 payload .bin",
    )
    parser.add_argument("output", type=pathlib.Path, help="destination PNG")
    parser.add_argument(
        "--offset",
        type=lambda value: int(value, 0),
        required=True,
        help="payload byte offset (decimal or 0xHEX)",
    )
    parser.add_argument(
        "--tiles",
        type=int,
        default=512,
        help="maximum number of 32-byte tiles to read (default: 512)",
    )
    parser.add_argument(
        "--tiles-wide",
        type=int,
        default=32,
        help="number of tiles per output row (default: 32)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="nearest-neighbor output scale (default: 2)",
    )
    args = parser.parse_args()

    if args.offset < 0:
        parser.error("--offset must be non-negative")
    if args.tiles <= 0:
        parser.error("--tiles must be positive")
    if args.tiles_wide <= 0:
        parser.error("--tiles-wide must be positive")
    if args.scale <= 0:
        parser.error("--scale must be positive")

    with args.input.open("rb") as source:
        source.seek(args.offset)
        raw = source.read(args.tiles * 32)
    tile_count = len(raw) // 32
    if tile_count == 0:
        parser.error("no complete 32-byte tile exists at the requested offset")
    rows = (tile_count + args.tiles_wide - 1) // args.tiles_wide
    image = Image.new("P", (args.tiles_wide * 8, rows * 8))
    palette = grayscale_palette()
    image.putpalette(palette)

    for index in range(tile_count):
        pixels = decode_tile(raw[index * 32 : index * 32 + 32])
        tile_image = Image.new("P", (8, 8))
        tile_image.putpalette(palette)
        tile_image.putdata(pixels)
        x = (index % args.tiles_wide) * 8
        y = (index // args.tiles_wide) * 8
        image.paste(tile_image, (x, y))

    if args.scale > 1:
        image = image.resize(
            (image.width * args.scale, image.height * args.scale),
            Image.Resampling.NEAREST,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)


if __name__ == "__main__":
    main()
