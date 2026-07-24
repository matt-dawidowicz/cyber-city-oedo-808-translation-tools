#!/usr/bin/env python3
"""Build a non-dialogue text inventory from the broad Shift-JIS scan.

``scan_likely_sjis.py`` intentionally finds both dialogue and standalone
labels. This command subtracts every byte interval already represented in
``dialogue.tsv`` so the remaining rows are useful as an auxiliary/UI/item/
location inventory.

The result is still heuristic. It may contain unused data, false positives,
or strings embedded in tables that require pointer-aware editing.

Both inputs are UTF-8 tab-separated files from the documented pipeline. The
command creates the output directory, replaces the destination TSV, and prints
summary counts. It does not read or modify the source disc image.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import pathlib
from collections.abc import Iterable

from game_layout import bank_for_offset


def parse_hex(value: str) -> int:
    """Parse a hexadecimal offset written by an upstream scanner.

    Args:
        value: String accepted by ``int(value, 16)``, normally ``0x...``.

    Returns:
        The corresponding integer byte offset.

    Raises:
        ValueError: If ``value`` is not a valid base-16 integer.
        TypeError: If ``value`` is not a string-like value accepted by
            ``int``.
    """

    return int(value, 16)


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent half-open byte ranges.

    Merging makes the later binary-search overlap test correct even if two
    candidate dialogue records happen to overlap.

    Args:
        ranges: Iterable of ``(start, end)`` half-open byte intervals.

    Returns:
        A start-sorted list of non-empty, non-overlapping ranges. Adjacent
        ranges are coalesced because no auxiliary byte can exist between them.

    Notes:
        Empty and reversed ranges are ignored instead of raising. Negative
        coordinates are retained and sorted because this low-level helper does
        not know which coordinate space the caller is validating.
    """

    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return merged


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser describing the dialogue-subtraction operation. Positional
        input and output paths are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Remove dialogue-covered byte ranges from a likely Shift-JIS scan "
            "to produce an auxiliary text inventory."
        )
    )


def main() -> None:
    """Subtract dialogue ranges and write the auxiliary-text inventory.

    Inputs:
        Parses paths for ``likely_shift_jis.tsv``, ``dialogue.tsv``, and the
        destination auxiliary TSV from the command line.

    Outputs:
        Writes non-overlapping broad-scan rows with their original payload
        coordinates plus a derived mission-bank label. Prints record, unique
        text, and character counts.

    Side Effects:
        Reads both input TSVs, creates the output parent directory, and
        replaces the destination TSV.

    Failure Conditions:
        File-system and CSV errors propagate. Missing columns raise
        ``KeyError``; malformed numeric fields raise ``ValueError``.
        Header-only inputs are valid and produce a header-only output.

    Design Decisions:
        Every dialogue interval, including ``review`` candidates, is removed.
        This prevents the same source bytes from appearing in both inventories
        even when dialogue confidence is low.
    """

    parser = build_parser()
    parser.add_argument(
        "likely_scan",
        type=pathlib.Path,
        help="TSV produced by scan_likely_sjis.py",
    )
    parser.add_argument(
        "dialogue",
        type=pathlib.Path,
        help="TSV produced by extract_dialogue.py",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination auxiliary TSV",
    )
    args = parser.parse_args()

    with args.dialogue.open("r", encoding="utf-8-sig", newline="") as source:
        dialogue_rows = list(csv.DictReader(source, delimiter="\t"))
    ranges = merge_ranges(
        (
            parse_hex(row["offset"]),
            parse_hex(row["offset"]) + int(row["record_bytes"]),
        )
        for row in dialogue_rows
    )
    range_starts = [start for start, _end in ranges]

    def covered(start: int, end: int) -> bool:
        """Return whether a half-open candidate overlaps dialogue.

        Args:
            start: First candidate byte offset.
            end: First byte after the candidate.

        Returns:
            ``True`` when ``[start, end)`` intersects any merged dialogue
            interval, otherwise ``False``.

        Assumptions:
            ``ranges`` is sorted and non-overlapping, and ``range_starts`` has
            the same order. ``bisect`` limits each query to the immediately
            preceding and following intervals.
        """

        index = bisect.bisect_right(range_starts, start) - 1
        if index >= 0 and ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(ranges) and ranges[next_index][0] < end

    output_rows: list[dict[str, object]] = []
    with args.likely_scan.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        for row in csv.DictReader(source, delimiter="\t"):
            offset = parse_hex(row["offset"])
            length = int(row["bytes"])
            if covered(offset, offset + length):
                continue
            output_rows.append(
                {
                    "bank": bank_for_offset(offset),
                    "offset": row["offset"],
                    "sector": row["sector"],
                    "within_sector": row["within_sector"],
                    "bytes": row["bytes"],
                    "characters": row["characters"],
                    "text": row["text"],
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "bank",
                "offset",
                "sector",
                "within_sector",
                "bytes",
                "characters",
                "text",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"records={len(output_rows)}")
    print(f"unique_texts={len({str(row['text']) for row in output_rows})}")
    print(f"characters={sum(int(row['characters']) for row in output_rows)}")


if __name__ == "__main__":
    main()
