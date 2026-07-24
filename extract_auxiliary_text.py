#!/usr/bin/env python3
"""Build a non-dialogue text inventory from the broad Shift-JIS scan.

``scan_likely_sjis.py`` intentionally finds both dialogue and standalone
labels.  This command subtracts every byte interval already represented in
``dialogue.tsv`` so the remaining rows are useful as an auxiliary/UI/item/
location inventory.

The result is still heuristic.  It may contain unused data, false positives,
or strings embedded in tables that require pointer-aware editing.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import pathlib
from collections.abc import Iterable

from game_layout import bank_for_offset


def parse_hex(value: str) -> int:
    """Parse the ``0x...`` offsets written by the scanners."""

    return int(value, 16)


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent half-open byte ranges.

    Merging makes the later binary-search overlap test correct even if two
    candidate dialogue records happen to overlap.
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
    """Build the command-line interface."""

    return argparse.ArgumentParser(
        description=(
            "Remove dialogue-covered byte ranges from a likely Shift-JIS scan "
            "to produce an auxiliary text inventory."
        )
    )


def main() -> None:
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
    parser.add_argument("output", type=pathlib.Path, help="destination auxiliary TSV")
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
        """Return whether ``[start, end)`` overlaps a dialogue byte range."""

        index = bisect.bisect_right(range_starts, start) - 1
        if index >= 0 and ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(ranges) and ranges[next_index][0] < end

    output_rows: list[dict[str, object]] = []
    with args.likely_scan.open("r", encoding="utf-8-sig", newline="") as source:
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
