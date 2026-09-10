#!/usr/bin/env python3
"""Subtract structured dialogue ranges from broad text candidates."""

from __future__ import annotations

import argparse
import bisect
import csv
import pathlib
from collections.abc import Iterable, Sequence

from cyber_oedo.disc.game_layout import bank_for_offset


def parse_hex(value: str) -> int:
    """Parse an upstream hexadecimal offset."""

    return int(value, 16)


def merge_ranges(
    ranges: Iterable[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Merge overlapping and adjacent non-empty half-open ranges."""

    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (
                previous_start,
                max(previous_end, end),
            )
        else:
            merged.append((start, end))
    return merged


def build_parser() -> argparse.ArgumentParser:
    """Build the auxiliary-text subtraction command parser."""

    return argparse.ArgumentParser(
        description=(
            "Remove dialogue-covered byte ranges from a likely "
            "Shift-JIS scan to produce an auxiliary text inventory."
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Stream non-dialogue broad-scan rows to the auxiliary inventory."""

    parser = build_parser()
    parser.add_argument("likely_scan", type=pathlib.Path)
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args(argv)

    with args.dialogue.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        reader = csv.DictReader(source, delimiter="\t")
        ranges = merge_ranges(
            (
                parse_hex(row["offset"]),
                parse_hex(row["offset"]) + int(row["record_bytes"]),
            )
            for row in reader
        )
    range_starts = [start for start, _ in ranges]

    def covered(start: int, end: int) -> bool:
        """Return whether a candidate overlaps merged dialogue ranges."""

        index = (
            bisect.bisect_right(
                range_starts,
                start,
            )
            - 1
        )
        if index >= 0 and ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(ranges) and ranges[next_index][0] < end

    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    character_count = 0
    unique_texts: set[str] = set()
    fieldnames = (
        "bank",
        "offset",
        "sector",
        "within_sector",
        "bytes",
        "characters",
        "text",
    )
    with (
        args.likely_scan.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as source,
        args.output.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as output,
    ):
        reader = csv.DictReader(source, delimiter="\t")
        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            delimiter="\t",
        )
        writer.writeheader()
        for row in reader:
            offset = parse_hex(row["offset"])
            length = int(row["bytes"])
            if covered(offset, offset + length):
                continue
            writer.writerow(
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
            count += 1
            character_count += int(row["characters"])
            unique_texts.add(row["text"])
    print(f"records={count}")
    print(f"unique_texts={len(unique_texts)}")
    print(f"characters={character_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
