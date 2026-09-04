"""Build a non-dialogue text inventory from a broad Shift-JIS scan."""

from __future__ import annotations

import argparse
import bisect
import csv
import pathlib
from collections.abc import Iterable

from cyber_oedo.disc.game_layout import bank_for_offset


def parse_hex(value: str) -> int:
    """Parse a hexadecimal payload offset."""

    return int(value, 16)


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent half-open byte ranges."""

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
    """Build the auxiliary-text command-line parser."""

    parser = argparse.ArgumentParser(
        description="Remove dialogue-covered ranges from a broad text scan."
    )
    parser.add_argument("likely_scan", type=pathlib.Path)
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    return parser


def main() -> None:
    """Subtract dialogue ranges and write the auxiliary-text inventory."""

    args = build_parser().parse_args()
    with args.dialogue.open("r", encoding="utf-8-sig", newline="") as source:
        dialogue_rows = list(csv.DictReader(source, delimiter="\t"))

    ranges = merge_ranges(
        (
            parse_hex(row["offset"]),
            parse_hex(row["offset"]) + int(row["record_bytes"]),
        )
        for row in dialogue_rows
    )
    range_starts = [start for start, _ in ranges]

    def covered(start: int, end: int) -> bool:
        """Return whether a half-open candidate overlaps dialogue."""

        index = bisect.bisect_right(range_starts, start) - 1
        if index >= 0 and ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(ranges) and ranges[next_index][0] < end

    rows: list[dict[str, object]] = []
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
            rows.append(
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

    fieldnames = (
        "bank",
        "offset",
        "sector",
        "within_sector",
        "bytes",
        "characters",
        "text",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    print(f"records={len(rows)}")
    print(f"unique_texts={len({str(row['text']) for row in rows})}")
    print(f"characters={sum(int(row['characters']) for row in rows)}")


if __name__ == "__main__":
    main()
