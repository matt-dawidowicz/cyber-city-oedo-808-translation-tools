#!/usr/bin/env python3
"""Exploratory scanner for byte-reversed two-byte Shift-JIS candidates.

This utility tested an early hypothesis that glyph codes might be stored as
little-endian 16-bit values (trail byte followed by lead byte). The game's
canonical text was subsequently confirmed to use normal byte-order Shift-JIS,
so this command is *not* part of the translation extraction pipeline.

Keep it only as a diagnostic for unidentified binary tables. Its output has a
high false-positive rate and must never be fed directly to the translation
inventory or treated as evidence of a patchable text format.

Input is an arbitrary binary payload. Output is a UTF-8-with-BOM TSV containing
payload-relative candidate addresses and decoded text. The command reads the
input into memory, creates the destination directory, replaces the requested
TSV, and prints a candidate count.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import unicodedata
from collections.abc import Iterator

from game_layout import SECTOR_SIZE


def decode_reversed_pair(low: int, high: int) -> str | None:
    """Decode one hypothesized trail-byte/lead-byte pair.

    Args:
        low: Byte stored first and interpreted as the Shift-JIS trail byte.
        high: Byte stored second and interpreted as the Shift-JIS lead byte.

    Returns:
        The decoded Unicode character when both ranges and the codec accept the
        reversed pair; otherwise ``None``.

    Notes:
        Integers outside byte range naturally fail the range checks. Codec
        errors are converted to ``None`` so exploratory scans can continue.
    """

    if not (
        (0x81 <= high <= 0x9F or 0xE0 <= high <= 0xEF)
        and (0x40 <= low <= 0x7E or 0x80 <= low <= 0xFC)
    ):
        return None
    try:
        return bytes((high, low)).decode("shift_jis")
    except UnicodeDecodeError:
        return None


def is_plausible_japanese(character: str) -> bool:
    """Classify a decoded character for exploratory run building.

    Args:
        character: Exactly one Unicode character.

    Returns:
        ``True`` for CJK punctuation, Kana, CJK Extension A, common
        ideographs, fullwidth forms, or any Unicode punctuation category.

    Raises:
        TypeError: If ``character`` does not contain exactly one character.

    Notes:
        The broad punctuation rule increases recall and false positives. This
        is appropriate only for testing an unconfirmed storage hypothesis.
    """

    code = ord(character)
    return (
        0x3000 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xFF01 <= code <= 0xFF60
        or unicodedata.category(character).startswith("P")
    )


def scan(data: bytes, minimum: int) -> Iterator[tuple[int, str]]:
    """Yield aligned runs of reversed Shift-JIS pairs.

    Both even and odd byte alignments are searched because an unidentified
    table need not begin at an even payload offset.

    Args:
        data: Binary payload to inspect.
        minimum: Minimum number of consecutive decoded pairs in a result.

    Yields:
        Tuples containing the run's payload offset and decoded Unicode text.

    Raises:
        ValueError: If ``minimum`` is not positive.

    Design Decisions:
        Each alignment advances in two-byte steps. After a failed or emitted
        run, the cursor advances at least one pair from its start, guaranteeing
        progress without mixing even and odd alignments.
    """

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    for alignment in (0, 1):
        offset = alignment
        while offset + 1 < len(data):
            start = offset
            characters: list[str] = []
            while offset + 1 < len(data):
                character = decode_reversed_pair(
                    data[offset],
                    data[offset + 1],
                )
                if character is None or not is_plausible_japanese(character):
                    break
                characters.append(character)
                offset += 2
            if len(characters) >= minimum:
                yield start, "".join(characters)
            offset = max(offset + 2, start + 2)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser that prominently identifies the scanner as experimental and
        non-canonical. Paths and thresholds are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "EXPERIMENTAL: scan for two-byte Shift-JIS pairs stored in "
            "reverse byte order."
        ),
        epilog=(
            "Do not use this output for the canonical translation inventory; "
            "the game's confirmed text uses normal Shift-JIS byte order."
        ),
    )


def main() -> None:
    """Run the exploratory reversed-pair scan.

    Inputs:
        Parses an input payload path, destination TSV, and minimum run length
        from command-line arguments.

    Outputs:
        Writes candidate offsets, sector coordinates, character counts, and
        decoded text. Prints the retained candidate count.

    Side Effects:
        Reads the complete input into memory, creates the output parent
        directory, and replaces the destination TSV.

    Failure Conditions:
        ``argparse`` exits for a non-positive minimum. File-system and CSV
        errors propagate.

    Notes:
        ``list(scan(...))`` materializes candidates before output so argument
        validation completes before any destination file is created.
    """

    parser = build_parser()
    parser.add_argument(
        "input",
        type=pathlib.Path,
        help="binary payload to inspect",
    )
    parser.add_argument("output", type=pathlib.Path, help="destination TSV")
    parser.add_argument(
        "--minimum",
        type=int,
        default=4,
        metavar="N",
        help="minimum consecutive reversed pairs (default: 4)",
    )
    args = parser.parse_args()

    data = args.input.read_bytes()
    try:
        candidates = list(scan(data, args.minimum))
    except ValueError as error:
        parser.error(str(error))

    rows: list[dict[str, object]] = []
    for offset, candidate_text in candidates:
        rows.append(
            {
                "offset": f"0x{offset:08X}",
                "sector": offset // SECTOR_SIZE,
                "within_sector": f"0x{offset % SECTOR_SIZE:03X}",
                "characters": len(candidate_text),
                "text": candidate_text,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
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
        writer.writerows(rows)
    print(f"strings={len(rows)}")


if __name__ == "__main__":
    main()
