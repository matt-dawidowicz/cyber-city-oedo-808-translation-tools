"""Analyze complete Mission 0 load-to-dialogue transition latency.

The earlier CD-load profiler correctly identified repeated reads, but its
headline hot-scene number measured only the spacing between CD_READ *starts*.
That is not the same as the black-screen / transition latency perceived by a
player.

This module extracts the repeatable Mission 0 five-read dialogue-load pattern
from historical Mesen captures and measures from the first CD request to the
first parser execution of the newly loaded dialogue.  It also reports the tiny
1x streaming floor so seek/command/setup overhead is visible explicitly.
"""

from __future__ import annotations

import argparse
import json
import math
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

# Mission 0's repeatedly observed dialogue/portrait load shape:
#
#   1425 -> 8000   common module, one local sector request
#   1426 -> 29D0   adjacent continuation/scratch sector
#   10xx -> 29D0   small event/dialogue resource (e.g. H_BARTEN)
#   1441 -> 9000   common 2-sector dialogue/UI block
#   1458/1561 ...  portrait/UI graphics into VRAM $4000
#
# The third and fifth sources vary by conversation/portrait, while the shape
# and destinations remain stable in the historical Mission 0 route.
M0_DIALOGUE_DESTINATION_PATTERN = (
    0x8000,
    0x29D0,
    0x29D0,
    0x9000,
    0x4000,
)
M0_DIALOGUE_TYPE_PATTERN = (0x01, 0x01, 0x01, 0x01, 0xFE)
M0_DIALOGUE_SECTOR_COUNT_PATTERN = (1, 1, 1, 2, 5)
M0_DIALOGUE_FIXED_SOURCES = {
    0: 0x1425,
    1: 0x1426,
    3: 0x1441,
}
M0_EVENT_RESOURCE_RANGE = range(0x1000, 0x1200)
M0_PORTRAIT_SOURCES = {0x1458, 0x1561}


@dataclass(frozen=True, slots=True)
class DialogueGroupStart:
    group: int
    frame: int


@dataclass(frozen=True, slots=True)
class DialogueLoadWindow:
    """One five-read Mission 0 dialogue-load sequence."""

    reads: tuple[CdRead, ...]
    dialogue_group: DialogueGroupStart

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


def parse_dialogue_group_starts(text: str) -> tuple[DialogueGroupStart, ...]:
    return tuple(
        DialogueGroupStart(
            group=int(match.group("group")),
            frame=int(match.group("frame")),
        )
        for match in _DIALOGUE_GROUP_RE.finditer(text)
    )


def _matches_m0_dialogue_bundle(reads: tuple[CdRead, ...]) -> bool:
    if len(reads) != 5:
        return False
    if tuple(item.destination for item in reads) != M0_DIALOGUE_DESTINATION_PATTERN:
        return False
    if tuple(item.address_type for item in reads) != M0_DIALOGUE_TYPE_PATTERN:
        return False
    if tuple(item.transfer_sectors for item in reads) != M0_DIALOGUE_SECTOR_COUNT_PATTERN:
        return False
    for index, expected in M0_DIALOGUE_FIXED_SOURCES.items():
        if reads[index].sector != expected:
            return False
    if reads[2].sector not in M0_EVENT_RESOURCE_RANGE:
        return False
    return reads[4].sector in M0_PORTRAIT_SOURCES


def find_m0_dialogue_load_windows(text: str) -> tuple[DialogueLoadWindow, ...]:
    """Find source-backed five-read loads followed by their dialogue-ready mark.

    Reads may be split across the historical profiler's burst IDs because that
    profiler starts a new burst after a 90-frame gap.  The actual five-read
    dialogue transition spans two such historical bursts.
    """

    reads = parse_cd_read_log(text)
    groups = parse_dialogue_group_starts(text)
    windows: list[DialogueLoadWindow] = []

    for index in range(0, len(reads) - 4):
        candidate = tuple(reads[index : index + 5])
        if not _matches_m0_dialogue_bundle(candidate):
            continue
        # The dialogue parser should become active shortly after the fifth
        # read.  Keep a generous 240-frame ceiling for historical captures
        # while rejecting a later unrelated conversation.
        ready = next(
            (
                group
                for group in groups
                if candidate[-1].frame < group.frame <= candidate[-1].frame + 240
            ),
            None,
        )
        if ready is None:
            continue
        windows.append(DialogueLoadWindow(candidate, ready))

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
    windows = find_m0_dialogue_load_windows(text)
    if not windows:
        raise ValueError("no Mission 0 dialogue-load windows were found")

    rows = []
    for window in windows:
        rows.append(
            {
                "dialogue_group": window.dialogue_group.group,
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
    seek_distances = [item.absolute_seek_distance for item in windows]
    stream_sectors = windows[0].transfer_sectors
    return {
        "window_count": len(windows),
        "measured_load_to_dialogue_frames": latencies,
        "measured_load_to_dialogue_seconds": [
            frames / 60.0 for frames in latencies
        ],
        "minimum_frames": min(latencies),
        "maximum_frames": max(latencies),
        "mean_frames": sum(latencies) / len(latencies),
        "mean_seconds": sum(latencies) / len(latencies) / 60.0,
        "streaming_floor": {
            "sectors": stream_sectors,
            "bytes": stream_sectors * SECTOR_BYTES,
            "seconds_at_1x": stream_sectors / CD_SECTORS_PER_SECOND,
            "frames_at_60hz": (
                stream_sectors / CD_SECTORS_PER_SECOND * 60.0
            ),
        },
        "mean_excess_seconds_over_stream_floor": (
            sum(item.excess_over_stream_frames for item in windows)
            / len(windows)
            / 60.0
        ),
        "source_seek_distance_sectors": seek_distances,
        "interpretation": (
            "The repeated dialogue transition moves only ten source sectors, "
            "yet takes roughly six seconds from first CD_READ to parser-ready. "
            "The source order oscillates hundreds of sectors backward and "
            "forward, so seek/command/setup and post-read work dominate raw "
            "1x streaming time."
        ),
        "windows": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure full Mission 0 CD-load-to-dialogue latency from Mesen logs."
        )
    )
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
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
