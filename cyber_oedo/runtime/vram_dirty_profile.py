"""Analyze dialogue VRAM-clobber profiler logs.

The live Mesen profiler records every VRAM byte changed between dialogue-load
start and the stock full exploration-image restore. This module turns those
raw ranges into an actionable selective-restore budget.

The analysis is deliberately independent of the future copy mechanism. It can
answer how many bytes actually need restoration and how much of the stock
0xEE00-byte scene reload is avoidable before choosing RAM-to-VRAM code.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

SCENE_RESTORE_BYTES = 0xEE00

_SUMMARY_RE = re.compile(
    r"\[VRAM_DIRTY_SUMMARY\s+(?P<session>\d+)\].*?"
    r"unique_changed_bytes=(?P<unique>\d+).*?"
    r"all_writes=(?P<writes>\d+).*?"
    r"changed_writes=(?P<changed>\d+)"
)
_RANGE_RE = re.compile(
    r"\[VRAM_DIRTY_RANGE\s+(?P<ordinal>\d+)\]\s+"
    r"byte=\$(?P<start>[0-9A-Fa-f]+)-\$(?P<end>[0-9A-Fa-f]+)\s+"
    r"bytes=(?P<bytes>\d+)"
)
_TOTAL_RE = re.compile(r"\[VRAM_DIRTY_RANGES_TOTAL\]\s+(?P<count>\d+)")


@dataclass(frozen=True, slots=True)
class DirtyRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid dirty VRAM range")

    @property
    def byte_count(self) -> int:
        return self.end - self.start + 1


def merge_ranges(
    ranges: tuple[DirtyRange, ...],
    *,
    maximum_gap: int = 0,
) -> tuple[DirtyRange, ...]:
    """Merge overlapping/nearby ranges for a future restore operation."""

    if maximum_gap < 0:
        raise ValueError("maximum_gap must be non-negative")
    if not ranges:
        return ()
    ordered = sorted(ranges, key=lambda item: (item.start, item.end))
    merged: list[DirtyRange] = []
    current = ordered[0]
    for item in ordered[1:]:
        if item.start <= current.end + maximum_gap + 1:
            current = DirtyRange(current.start, max(current.end, item.end))
        else:
            merged.append(current)
            current = item
    merged.append(current)
    return tuple(merged)


def _aligned_range(item: DirtyRange, alignment: int) -> DirtyRange:
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    start = item.start & ~(alignment - 1)
    end_exclusive = (item.end + 1 + alignment - 1) & ~(alignment - 1)
    return DirtyRange(start, end_exclusive - 1)


def build_vram_dirty_report(
    text: str,
    *,
    merge_gap: int = 0,
    transfer_alignment: int = 2,
) -> dict[str, object]:
    """Parse one or more profiler sessions into selective-restore metrics."""

    sessions: list[dict[str, object]] = []
    current_ranges: list[DirtyRange] = []
    pending_summary: dict[str, int] | None = None

    for line in text.splitlines():
        summary = _SUMMARY_RE.search(line)
        if summary:
            pending_summary = {
                "session": int(summary.group("session")),
                "unique_changed_bytes": int(summary.group("unique")),
                "all_writes": int(summary.group("writes")),
                "changed_writes": int(summary.group("changed")),
            }
            current_ranges = []
            continue

        match = _RANGE_RE.search(line)
        if match and pending_summary is not None:
            item = DirtyRange(
                start=int(match.group("start"), 16),
                end=int(match.group("end"), 16),
            )
            if item.byte_count != int(match.group("bytes")):
                raise ValueError("VRAM dirty range byte count mismatch")
            current_ranges.append(item)
            continue

        total = _TOTAL_RE.search(line)
        if total and pending_summary is not None:
            expected_count = int(total.group("count"))
            if expected_count != len(current_ranges):
                raise ValueError("VRAM dirty range count mismatch")

            exact = merge_ranges(tuple(current_ranges), maximum_gap=0)
            grouped = merge_ranges(tuple(current_ranges), maximum_gap=merge_gap)
            aligned = merge_ranges(
                tuple(_aligned_range(item, transfer_alignment) for item in grouped),
                maximum_gap=0,
            )
            exact_bytes = sum(item.byte_count for item in exact)
            grouped_bytes = sum(item.byte_count for item in grouped)
            aligned_bytes = sum(item.byte_count for item in aligned)
            unique = pending_summary["unique_changed_bytes"]
            if exact_bytes != unique:
                raise ValueError(
                    "merged dirty range bytes do not equal profiler unique count"
                )

            sessions.append(
                {
                    **pending_summary,
                    "raw_range_count": len(current_ranges),
                    "exact_merged_range_count": len(exact),
                    "grouped_range_count": len(grouped),
                    "aligned_range_count": len(aligned),
                    "grouped_bytes": grouped_bytes,
                    "aligned_restore_bytes": aligned_bytes,
                    "stock_scene_restore_bytes": SCENE_RESTORE_BYTES,
                    "bytes_avoided_vs_stock": SCENE_RESTORE_BYTES - aligned_bytes,
                    "restore_reduction_percent":
                        (SCENE_RESTORE_BYTES - aligned_bytes)
                        / SCENE_RESTORE_BYTES
                        * 100.0,
                    "aligned_ranges": [
                        {
                            "start": f"0x{item.start:04X}",
                            "end": f"0x{item.end:04X}",
                            "bytes": item.byte_count,
                        }
                        for item in aligned
                    ],
                }
            )
            pending_summary = None
            current_ranges = []

    if pending_summary is not None:
        raise ValueError("truncated VRAM dirty session without range total")
    if not sessions:
        raise ValueError("no complete VRAM dirty sessions found")

    return {
        "session_count": len(sessions),
        "merge_gap": merge_gap,
        "transfer_alignment": transfer_alignment,
        "stock_scene_restore_bytes": SCENE_RESTORE_BYTES,
        "sessions": sessions,
        "best_aligned_restore_bytes": min(
            item["aligned_restore_bytes"] for item in sessions
        ),
        "worst_aligned_restore_bytes": max(
            item["aligned_restore_bytes"] for item in sessions
        ),
        "caveat": (
            "Dirty ranges prove what changed in the captured route only. "
            "A release fast path must union representative interactions and "
            "restore from a source whose lifetime is independently proven."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze Cyber City Oedo 808 dialogue VRAM dirty logs."
    )
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--merge-gap", type=int, default=0)
    parser.add_argument("--alignment", type=int, default=2)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_vram_dirty_report(
        args.log.read_text(encoding="utf-8", errors="replace"),
        merge_gap=args.merge_gap,
        transfer_alignment=args.alignment,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
