"""Render candidate PC Engine 4bpp tiles for visual inspection."""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image

from cyber_oedo.graphics.pce_graphics import decode_tile


def grayscale_palette() -> list[int]:
    """Build a synthetic 16-step grayscale diagnostic palette."""

    palette: list[int] = []
    for value in range(16):
        shade = round(value * 255 / 15)
        palette.extend((shade, shade, shade))
    palette.extend([0] * (768 - len(palette)))
    return palette


def build_parser() -> argparse.ArgumentParser:
    """Build the tile-renderer command-line parser."""

    parser = argparse.ArgumentParser(
        description="Render raw 32-byte PC Engine 4bpp tiles."
    )
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument(
        "--offset",
        type=lambda value: int(value, 0),
        required=True,
    )
    parser.add_argument("--tiles", type=int, default=512)
    parser.add_argument("--tiles-wide", type=int, default=32)
    parser.add_argument("--scale", type=int, default=2)
    return parser


def main() -> None:
    """Render complete 4bpp tiles from an arbitrary payload offset."""

    parser = build_parser()
    args = parser.parse_args()
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    if args.tiles <= 0 or args.tiles_wide <= 0 or args.scale <= 0:
        parser.error("tile count, width, and scale must be positive")

    with args.input.open("rb") as source:
        source.seek(args.offset)
        raw = source.read(args.tiles * 32)
    tile_count = len(raw) // 32
    if tile_count == 0:
        parser.error("no complete tile exists at the requested offset")

    rows = (tile_count + args.tiles_wide - 1) // args.tiles_wide
    image = Image.new("P", (args.tiles_wide * 8, rows * 8))
    palette = grayscale_palette()
    image.putpalette(palette)

    for index in range(tile_count):
        pixels = decode_tile(raw[index * 32 : index * 32 + 32])
        tile = Image.new("P", (8, 8))
        tile.putpalette(palette)
        tile.putdata(pixels)
        image.paste(
            tile,
            ((index % args.tiles_wide) * 8, (index // args.tiles_wide) * 8),
        )

    if args.scale > 1:
        image = image.resize(
            (image.width * args.scale, image.height * args.scale),
            Image.Resampling.NEAREST,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.output)


if __name__ == "__main__":
    main()
