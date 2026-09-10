#!/usr/bin/env python3
"""Combine rendered PNGs into a labeled reverse-engineering contact sheet.

Files are sorted by name, so naming tile renders with their offsets (for
example ``00145800.png``) produces an address-ordered sheet. If the output is
inside the input directory, it is excluded from the input list to prevent a
previous contact sheet from being recursively embedded on the next run.

The command requires Pillow, loads every input PNG into memory, creates the
destination directory, and replaces the requested output image. It does not
modify source renders.
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw


def load_rgb(path: pathlib.Path) -> Image.Image:
    """Load an image as detached RGB pixel data.

    Args:
        path: Source image understood by Pillow.

    Returns:
        A new RGB ``Image`` whose pixel data no longer depends on an open file
        handle.

    Raises:
        OSError: If Pillow cannot open, decode, or read the source image.

    Side Effects:
        Opens the source file temporarily and closes it before returning.

    Design Decisions:
        Converting inside the context manager prevents Pillow's lazy-loading
        behavior from leaving many source files open while the sheet is built.
    """

    with Image.open(path) as source:
        return source.convert("RGB")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser describing alphabetical PNG aggregation. Paths and column
        count are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=("Combine alphabetically sorted PNGs into a labeled contact sheet.")
    )


def main() -> None:
    """Combine a directory of PNG renders into a labeled sheet.

    Inputs:
        Parses an input directory, output PNG path, and positive column count
        from command-line arguments.

    Outputs:
        Writes one RGB PNG with filename-stem labels above each source render.
        Normal success produces no console output.

    Side Effects:
        Opens every matching PNG, keeps converted images in memory, creates the
        output parent directory, and replaces the destination image.

    Failure Conditions:
        ``argparse`` exits for a non-positive column count or when no input
        PNG remains after output exclusion. File-system and Pillow errors
        propagate.

    Design Decisions:
        Input files are sorted lexically for deterministic, address-friendly
        ordering. Cell dimensions use the largest source image, smaller images
        stay top-left aligned, and Pillow's default font renders labels. Only
        the exact resolved output path is excluded; other PNG sheets are valid
        inputs unless moved or renamed.
    """

    parser = build_parser()
    parser.add_argument(
        "input_dir",
        type=pathlib.Path,
        help="directory of PNG renders",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination contact-sheet PNG",
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=4,
        help="number of cells per row (default: 4)",
    )
    args = parser.parse_args()

    if args.columns <= 0:
        parser.error("--columns must be positive")
    output_resolved = args.output.resolve()
    paths = [
        path
        for path in sorted(args.input_dir.glob("*.png"))
        if path.resolve() != output_resolved
    ]
    if not paths:
        parser.error("no input PNG files found")
    images = [(path, load_rgb(path)) for path in paths]
    label_height = 24
    cell_width = max(image.width for _, image in images)
    cell_height = max(image.height for _, image in images) + label_height
    rows = (len(images) + args.columns - 1) // args.columns
    sheet = Image.new(
        "RGB",
        (cell_width * args.columns, cell_height * rows),
        "white",
    )
    draw = ImageDraw.Draw(sheet)
    for index, (path, image) in enumerate(images):
        x = (index % args.columns) * cell_width
        y = (index // args.columns) * cell_height
        draw.text((x + 4, y + 4), path.stem, fill="black")
        sheet.paste(image, (x, y + label_height))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)


if __name__ == "__main__":
    main()
