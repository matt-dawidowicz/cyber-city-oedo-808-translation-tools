#!/usr/bin/env python3
"""Exploratory scanner for byte-reversed Shift-JIS candidates."""

from __future__ import annotations

import argparse
import csv
import pathlib
import unicodedata
from collections.abc import Iterator, Sequence

from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file
from cyber_oedo.text.sjis import (
    is_shift_jis_lead,
    is_shift_jis_trail,
)


def decode_reversed_pair(low: int, high: int) -> str | None:
    """Decode one hypothesized trail-byte/lead-byte pair."""

    if not is_shift_jis_lead(high) or not is_shift_jis_trail(low):
        return None
    try:
        return bytes((high, low)).decode("shift_jis")
    except UnicodeDecodeError:
        return None


def is_plausible_japanese(character: str) -> bool:
    """Classify a decoded character for exploratory run building."""

    code = ord(character)
    return (
        0x3000 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xFF01 <= code <= 0xFF60
        or unicodedata.category(character).startswith("P")
    )


def scan(
    data: object,
    minimum: int,
) -> Iterator[tuple[int, str]]:
    """Yield aligned runs of reversed Shift-JIS pairs."""

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    size = len(data)  # type: ignore[arg-type]
    for alignment in (0, 1):
        offset = alignment
        while offset + 1 < size:
            start = offset
            characters: list[str] = []
            while offset + 1 < size:
                character = decode_reversed_pair(
                    data[offset],  # type: ignore[index]
                    data[offset + 1],  # type: ignore[index]
                )
                if (
                    character is None
                    or not is_plausible_japanese(character)
                ):
                    break
                characters.append(character)
                offset += 2
            if len(characters) >= minimum:
                yield start, "".join(characters)
            offset = max(offset + 2, start + 2)


def build_parser() -> argparse.ArgumentParser:
    """Build the experimental reversed-code scanner parser."""

    return argparse.ArgumentParser(
        description=(
            "EXPERIMENTAL: scan for two-byte Shift-JIS pairs stored "
            "in reverse byte order."
        ),
        epilog=(
            "Do not use this output for the canonical translation "
            "inventory; confirmed text uses normal Shift-JIS order."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Memory-map input and stream exploratory candidates to TSV."""

    parser = build_parser()
    parser.add_argument(
        "input",
        type=pathlib.Path,
        help="binary payload to inspect",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination TSV",
    )
    parser.add_argument(
        "--minimum",
        type=int,
        default=4,
        metavar="N",
        help="minimum consecutive reversed pairs (default: 4)",
    )
    args = parser.parse_args(argv)
    if args.minimum <= 0:
        parser.error("--minimum must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with mapped_file(args.input) as data, args.output.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "offset",
                "sector",
                "within_sector",
                "characters",
                "text",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        for offset, candidate_text in scan(data, args.minimum):
            writer.writerow(
                {
                    "offset": f"0x{offset:08X}",
                    "sector": offset // SECTOR_SIZE,
                    "within_sector": (
                        f"0x{offset % SECTOR_SIZE:03X}"
                    ),
                    "characters": len(candidate_text),
                    "text": candidate_text,
                }
            )
            count += 1
    print(f"strings={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
