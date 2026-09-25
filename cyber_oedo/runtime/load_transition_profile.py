"""Analyze complete Mission 0 load-to-dialogue transition latency.

The earlier CD-load profiler correctly identified repeated reads, but its
headline hot-scene number measured only the spacing between CD_READ *starts*.
That is not the same as the black-screen / transition latency perceived by a
player.

Historical Mission 0 captures show two forms of the same dialogue transition:

* cold event resource: 1425, 1426, 10xx, 1441, portrait;
* cached event resource: 1425, 1426, 1441, portrait.

The resource cache can therefore remove the 10xx read entirely while the
transition still takes roughly 5.7 seconds.  This module recognizes both forms
and measures from the first CD request to the first parser execution.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass

from cyber_oedo.runtime.cd_load_profile import (
    CD_SECTORS_PER_SECOND,
    SECTOR_BYTES,
    CdRead,
    parse_cd_read_log,
)

_DIALOGUE_GROUP_RE = re.compile(
    r"DIALOGUE GROUP\s+(?P<group>\d+)\s+START\s+frame=(?P<frame>\d+)"
)

M0_MODULE_FIRST = (0x1425, 0x8000, 0x01, 1)
M0_MODULE_REMAINDER = (0x1426, 0x29D0, 0x01, 1)
M0_COMMON_BLOCK = (0x1441, 0x9000, 0x01, 2)
M0_EVENT_RESOURCE_RANGE = range(0x1000, 0x1200)
M0_PORTRAIT_SOURCES = {0x1458, 0x1561}


@dataclass(frozen=True, slots=True)
class DialogueGroupStart:
    """Record the first parser frame of one separated dialogue group."""

    group: int
    frame: int


@dataclass(frozen=True, slots=True)
class DialogueLoadWindow:
    """One cold or cache-hit Mission 0 dialogue-load sequence."""

    reads: tuple[CdRead, ...]
    dialogue_group: DialogueGroupStart
    event_resource_read: CdRead | None

    @property
    def first_frame(self) -> int:
        return self.reads[0].frame

    @property
    def last_read_start_frame(self) -> int:
        return self.reads[-1].frame

    @property
    def ready_frame(self) -> int:
        return self.dialogue_group.frame

    @property
    def load_to_ready_frames(self) -> int:
        return self.ready_frame - self.first_frame

    @property
    def load_to_ready_seconds(self) -> float:
        return self.load_to_ready_frames / 60.0

    @property
    def transfer_sectors(self) -> int:
        return sum(item.transfer_sectors for item in self.reads)

    @property
    def pure_stream_seconds(self) -> float:
        return self.transfer_sectors / CD_SECTORS_PER_SECOND

    @property
    def pure_stream_frames(self) -> float:
        return self.pure_stream_seconds * 60.0

    @property
    def excess_over_stream_frames(self) -> float:
        return self.load_to_ready_frames - self.pure_stream_frames

    @property
    def source_start_deltas(self) -> tuple[int, ...]:
        return tuple(
            right.sector - left.sector
            for left, right in zip(self.reads, self.reads[1:])
        )

    @property
    def absolute_seek_distance(self) -> int:
        return sum(abs(delta) for delta in self.source_start_deltas)

    @property
    def event_cache_hit(self) -> bool:
        return self.event_resource_read is None


def parse_dialogue_group_starts(text: str) -> tuple[DialogueGroupStart, ...]:
    """Extract historical dialogue-group start markers from a Mesen log."""

    return tuple(
        DialogueGroupStart(
            group=int(match.group("group")),
            frame=int(match.group("frame")),
        )
        for match in _DIALOGUE_GROUP_RE.finditer(text)
    )


def _matches(item: CdRead, signature: tuple[int, int, int, int]) -> bool:
    sector, destination, address_type, sectors = signature
    return (
        item.sector == sector
        and item.destination == destination
        and item.address_type == address_type
        and item.transfer_sectors == sectors
    )


def _is_event_resource(item: CdRead) -> bool:
    return (
        item.sector in M0_EVENT_RESOURCE_RANGE
        and item.destination == 0x29D0
        and item.address_type == 0x01
        and item.transfer_sectors == 1
    )


def _is_portrait(item: CdRead) -> bool:
    return (
        item.sector in M0_PORTRAIT_SOURCES
        and item.destination == 0x4000
        and item.address_type == 0xFE
        and item.transfer_sectors == 5
    )


def find_m0_dialogue_load_windows(text: str) -> tuple[DialogueLoadWindow, ...]:
    """Find cold and cache-hit dialogue transitions.

    The historical profiler split a single player-visible transition into
    multiple "bursts" after a 90-frame gap, so burst IDs are intentionally
    ignored.  A window starts with the fixed 1425/1426 module load, optionally
    contains one 10xx named event resource read, and must then contain the
    fixed 1441 two-sector block and a recognized portrait read.
    """

    reads = parse_cd_read_log(text)
    groups = parse_dialogue_group_starts(text)
    windows: list[DialogueLoadWindow] = []

    index = 0
    while index < len(reads) - 3:
        if not _matches(reads[index], M0_MODULE_FIRST):
            index += 1
            continue
        if not _matches(reads[index + 1], M0_MODULE_REMAINDER):
            index += 1
            continue

        cursor = index + 2
        event_read: CdRead | None = None
        if cursor < len(reads) and _is_event_resource(reads[cursor]):
            event_read = reads[cursor]
            cursor += 1

        if cursor + 1 >= len(reads):
            break
        if not _matches(reads[cursor], M0_COMMON_BLOCK):
            index += 1
            continue
        if not _is_portrait(reads[cursor + 1]):
            index += 1
            continue

        candidate = tuple(reads[index : cursor + 2])
        ready = next(
            (
                group
                for group in groups
                if candidate[-1].frame < group.frame <= candidate[-1].frame + 240
            ),
            None,
        )
        if ready is not None:
            windows.append(
                DialogueLoadWindow(
                    reads=candidate,
                    dialogue_group=ready,
                    event_resource_read=event_read,
                )
            )
        index = cursor + 2

    return tuple(windows)


def _read_json(item: CdRead) -> dict[str, object]:
    return {
        "ordinal": item.ordinal,
        "frame": item.frame,
        "absolute_lba": f"0x{item.sector:04X}",
        "destination": f"0x{item.destination:04X}",
        "address_type": f"0x{item.address_type:02X}",
        "transfer_bytes": item.transfer_bytes,
        "transfer_sectors": item.transfer_sectors,
    }


def build_transition_latency_report(text: str) -> dict[str, object]:
    """Build cold/cache-hit load-to-parser timing evidence from one log."""

    windows = find_m0_dialogue_load_windows(text)
    if not windows:
        raise ValueError("no Mission 0 dialogue-load windows were found")

    rows = []
    for window in windows:
        rows.append(
            {
                "dialogue_group": window.dialogue_group.group,
                "event_cache_hit": window.event_cache_hit,
                "event_resource_lba": (
                    None
                    if window.event_resource_read is None
                    else f"0x{window.event_resource_read.sector:04X}"
                ),
                "first_cd_frame": window.first_frame,
                "last_cd_start_frame": window.last_read_start_frame,
                "dialogue_ready_frame": window.ready_frame,
                "load_to_ready_frames": window.load_to_ready_frames,
                "load_to_ready_seconds": window.load_to_ready_seconds,
                "transfer_sectors": window.transfer_sectors,
                "transfer_bytes": window.transfer_sectors * SECTOR_BYTES,
                "pure_1x_stream_frames": window.pure_stream_frames,
                "pure_1x_stream_seconds": window.pure_stream_seconds,
                "excess_frames_over_1x_stream_floor": window.excess_over_stream_frames,
                "excess_seconds_over_1x_stream_floor": (
                    window.excess_over_stream_frames / 60.0
                ),
                "source_start_deltas_sectors": list(window.source_start_deltas),
                "absolute_source_seek_distance_sectors": (
                    window.absolute_seek_distance
                ),
                "reads": [_read_json(item) for item in window.reads],
            }
        )

    latencies = [item.load_to_ready_frames for item in windows]
    cold = [item for item in windows if not item.event_cache_hit]
    cached = [item for item in windows if item.event_cache_hit]

    def mean_seconds(items: list[DialogueLoadWindow]) -> float | None:
        if not items:
            return None
        return sum(item.load_to_ready_frames for item in items) / len(items) / 60.0

    return {
        "window_count": len(windows),
        "cold_event_resource_windows": len(cold),
        "cached_event_resource_windows": len(cached),
        "measured_load_to_dialogue_frames": latencies,
        "measured_load_to_dialogue_seconds": [
            frames / 60.0 for frames in latencies
        ],
        "minimum_frames": min(latencies),
        "maximum_frames": max(latencies),
        "mean_frames": sum(latencies) / len(latencies),
        "mean_seconds": sum(latencies) / len(latencies) / 60.0,
        "cold_mean_seconds": mean_seconds(cold),
        "cached_mean_seconds": mean_seconds(cached),
        "mean_excess_seconds_over_stream_floor": (
            sum(item.excess_over_stream_frames for item in windows)
            / len(windows)
            / 60.0
        ),
        "source_seek_distance_sectors": [
            item.absolute_seek_distance for item in windows
        ],
        "interpretation": (
            "The named event-resource cache removes the 10xx CD read in later "
            "transitions, but cached transitions still take about 5.7 seconds. "
            "Therefore the cold 10xx seek is a real extra penalty, not the "
            "root cause of the baseline pause. BIOS command latency, hidden "
            "ADPCM transfers, display/audio orchestration, and post-read work "
            "must be timed separately."
        ),
        "windows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the transition-latency command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Measure full Mission 0 CD-load-to-dialogue latency from Mesen logs."
        )
    )
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run transition-latency analysis and emit JSON."""

    args = build_parser().parse_args(argv)
    report = build_transition_latency_report(
        args.log.read_text(encoding="utf-8", errors="replace")
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
