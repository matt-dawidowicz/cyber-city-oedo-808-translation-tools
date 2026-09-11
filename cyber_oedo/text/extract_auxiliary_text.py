#!/usr/bin/env python3
"""Subtract structured dialogue and proven dialogue shadows from broad text scans."""

from __future__ import annotations

import argparse
import bisect
import contextlib
import pathlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cyber_oedo.disc.game_layout import SECTOR_SIZE, bank_for_offset
from cyber_oedo.io import mapped_file
from cyber_oedo.tabular import tsv_dict_reader, tsv_dict_writer

CONTROL_TAG = re.compile(r"<\$[0-9A-Fa-f]{2}>")
DEFAULT_SHADOW_DISTANCE = SECTOR_SIZE
DEFAULT_SHADOW_ZERO_RUN = 32
OUTPUT_FIELDS = (
    "bank",
    "offset",
    "sector",
    "within_sector",
    "bytes",
    "characters",
    "text",
)
REJECTION_FIELDS = OUTPUT_FIELDS + (
    "rejection_reason",
    "resource_name",
    "matched_dialogue_offset",
    "distance_bytes",
    "tail_zero_bytes",
    "dangling_lead_byte",
)


@dataclass(frozen=True, slots=True)
class DialogueEvidence:
    """Source-guarded dialogue metadata used by the auxiliary filter."""

    start: int
    end: int
    text: str
    segments: tuple[bytes, ...]
    resource_start: int | None


@dataclass(frozen=True, slots=True)
class ShadowMatch:
    """Evidence tying one auxiliary run to a nearby structured-dialogue fragment."""

    resource_name: str
    dialogue_offset: int
    distance_bytes: int
    tail_zero_bytes: int
    dangling_lead_byte: int | None


@dataclass(frozen=True, slots=True)
class AuxiliaryStats:
    """Summary counters for one auxiliary extraction."""

    records: int
    unique_texts: int
    characters: int
    dialogue_overlaps: int
    dialogue_shadows: int


def parse_hex(value: str) -> int:
    """Parse an upstream hexadecimal offset."""

    return int(value, 16)


def merge_ranges(ranges: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping and adjacent non-empty half-open ranges."""

    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start >= end:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _resource_regions(
    path: pathlib.Path,
    *,
    data: object | None = None,
) -> tuple[tuple[int, int, str], ...]:
    """Read and validate sorted half-open candidate-resource intervals."""

    regions: list[tuple[int, int, str]] = []
    with tsv_dict_reader(path) as reader:
        for row in reader:
            start = parse_hex(row["resource_offset"])
            end = parse_hex(row["end_offset_exclusive"])
            if start >= end:
                raise ValueError(f"{path}: invalid resource interval at {row['resource_offset']}")
            name = row["resource_name"]
            if data is not None:
                if end > len(data):  # type: ignore[arg-type]
                    raise ValueError(
                        f"{path}: resource interval exceeds payload at {row['resource_offset']}"
                    )
                try:
                    expected_name = name.encode("ascii")
                except UnicodeEncodeError as error:
                    raise ValueError(
                        f"{path}: non-ASCII resource name at {row['resource_offset']}"
                    ) from error
                if bytes(data[start : start + len(expected_name)]) != expected_name:  # type: ignore[index]
                    raise ValueError(
                        f"{path}: resource source mismatch at {row['resource_offset']}"
                    )
            regions.append((start, end, name))
    regions.sort()
    if any(left[1] > right[0] for left, right in zip(regions, regions[1:])):
        raise ValueError(f"{path}: overlapping resource intervals")
    return tuple(regions)


def _find_region(
    regions: tuple[tuple[int, int, str], ...],
    starts: tuple[int, ...],
    start: int,
    end: int,
) -> tuple[int, int, str] | None:
    """Return the resource that wholly contains one byte interval."""

    index = bisect.bisect_right(starts, start) - 1
    if index < 0:
        return None
    region = regions[index]
    return region if region[0] <= start < end <= region[1] else None


def _text_segments(tagged_text: str) -> tuple[bytes, ...]:
    """Encode contiguous dialogue text runs without crossing control tags."""

    try:
        return tuple(
            part.encode("shift_jis")
            for part in CONTROL_TAG.split(tagged_text)
            if part
        )
    except UnicodeEncodeError as error:
        raise ValueError("dialogue tagged_text is not Shift-JIS encodable") from error


def _read_dialogue(
    path: pathlib.Path,
    *,
    data: object | None = None,
    regions: tuple[tuple[int, int, str], ...] = (),
    region_starts: tuple[int, ...] = (),
) -> tuple[DialogueEvidence, ...]:
    """Read dialogue rows, enforce ordering, and optionally source-guard them."""

    records: list[DialogueEvidence] = []
    previous = -1
    with tsv_dict_reader(path) as reader:
        for row in reader:
            start = parse_hex(row["offset"])
            if start < previous:
                raise ValueError(f"{path}: dialogue rows are not sorted by offset")
            previous = start
            end = start + int(row["record_bytes"])
            if data is not None:
                try:
                    expected = bytes.fromhex(row["raw_hex"])
                except ValueError as error:
                    raise ValueError(f"{path}: invalid raw_hex at {row['offset']}") from error
                if len(expected) != end - start or bytes(data[start:end]) != expected:  # type: ignore[index]
                    raise ValueError(f"{path}: dialogue source mismatch at {row['offset']}")
            region = _find_region(regions, region_starts, start, end) if regions else None
            records.append(
                DialogueEvidence(
                    start=start,
                    end=end,
                    text=row["text"],
                    segments=_text_segments(row["tagged_text"]),
                    resource_start=region[0] if region is not None else None,
                )
            )
    return tuple(records)


def _interval_distance(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    """Return the byte gap between two half-open intervals."""

    if a_end <= b_start:
        return b_start - a_end
    if b_end <= a_start:
        return a_start - b_end
    return 0


def _zero_tail(
    data: object,
    end: int,
    minimum: int,
    *,
    limit: int | None = None,
) -> tuple[int, int | None] | None:
    """Detect the long zero tail characteristic of truncated shadow copies."""

    size = len(data)  # type: ignore[arg-type]
    scan_limit = size if limit is None else min(size, limit)
    if end >= scan_limit:
        return None
    cursor = end
    dangling: int | None = None
    first = int(data[cursor])  # type: ignore[index]
    if 0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF:
        dangling = first
        cursor += 1
    zero_bytes = 0
    while (
        cursor + zero_bytes < scan_limit
        and data[cursor + zero_bytes] == 0  # type: ignore[index]
    ):
        zero_bytes += 1
    return (zero_bytes, dangling) if zero_bytes >= minimum else None


def _shadow_match(
    *,
    start: int,
    end: int,
    text: str,
    raw: bytes,
    regions: tuple[tuple[int, int, str], ...],
    region_starts: tuple[int, ...],
    dialogue_by_resource: dict[int, tuple[DialogueEvidence, ...]],
    distance_limit: int,
    tail: tuple[int, int | None],
) -> ShadowMatch | None:
    """Return conservative evidence that one broad run is a dialogue shadow."""

    region = _find_region(regions, region_starts, start, end)
    if region is None:
        return None
    best: ShadowMatch | None = None
    for record in dialogue_by_resource.get(region[0], ()):
        if text == record.text:
            continue
        distance = _interval_distance(start, end, record.start, record.end)
        if distance > distance_limit:
            continue
        if not any(raw in segment for segment in record.segments):
            continue
        match = ShadowMatch(region[2], record.start, distance, tail[0], tail[1])
        if best is None or match.distance_bytes < best.distance_bytes:
            best = match
    return best


def write_auxiliary_text(
    likely_scan: pathlib.Path,
    dialogue: pathlib.Path,
    output: pathlib.Path,
    *,
    resource_map: pathlib.Path | None = None,
    data: object | None = None,
    rejected_output: pathlib.Path | None = None,
    shadow_distance: int = DEFAULT_SHADOW_DISTANCE,
    shadow_zero_run: int = DEFAULT_SHADOW_ZERO_RUN,
) -> AuxiliaryStats:
    """Write auxiliary candidates after overlap and dialogue-shadow rejection."""

    if shadow_distance < 0:
        raise ValueError("shadow_distance must be non-negative")
    if shadow_zero_run <= 0:
        raise ValueError("shadow_zero_run must be positive")
    if (resource_map is None) != (data is None):
        raise ValueError("resource_map and data must be provided together")
    if rejected_output is not None and data is None:
        raise ValueError("rejected_output requires resource_map and data")

    regions = (
        _resource_regions(resource_map, data=data)
        if resource_map is not None
        else ()
    )
    region_starts = tuple(region[0] for region in regions)
    records = _read_dialogue(
        dialogue,
        data=data,
        regions=regions,
        region_starts=region_starts,
    )
    ranges = merge_ranges((record.start, record.end) for record in records)
    range_starts = tuple(start for start, _ in ranges)
    by_resource: dict[int, list[DialogueEvidence]] = {}
    for record in records:
        if record.resource_start is not None:
            by_resource.setdefault(record.resource_start, []).append(record)
    dialogue_by_resource = {key: tuple(value) for key, value in by_resource.items()}

    def covered(start: int, end: int) -> bool:
        index = bisect.bisect_right(range_starts, start) - 1
        if index >= 0 and ranges[index][1] > start:
            return True
        next_index = index + 1
        return next_index < len(ranges) and ranges[next_index][0] < end

    count = character_count = overlap_count = shadow_count = 0
    unique_texts: set[str] = set()
    with contextlib.ExitStack() as stack:
        reader = stack.enter_context(tsv_dict_reader(likely_scan))
        writer = stack.enter_context(tsv_dict_writer(output, OUTPUT_FIELDS))
        rejected = (
            stack.enter_context(tsv_dict_writer(rejected_output, REJECTION_FIELDS))
            if rejected_output is not None
            else None
        )
        previous_candidate = -1
        for row in reader:
            start = parse_hex(row["offset"])
            if start < previous_candidate:
                raise ValueError(f"{likely_scan}: candidate rows are not sorted by offset")
            previous_candidate = start
            length = int(row["bytes"])
            end = start + length
            if covered(start, end):
                overlap_count += 1
                continue

            shadow = None
            if data is not None:
                try:
                    encoded = row["text"].encode("shift_jis")
                except UnicodeEncodeError as error:
                    raise ValueError(
                        f"{likely_scan}: candidate is not encodable at {row['offset']}"
                    ) from error
                raw = bytes(data[start:end])  # type: ignore[index]
                if len(encoded) != length or raw != encoded:
                    raise ValueError(
                        f"{likely_scan}: candidate source mismatch at {row['offset']}"
                    )
                candidate_region = _find_region(
                    regions,
                    region_starts,
                    start,
                    end,
                )
                tail = (
                    _zero_tail(
                        data,
                        end,
                        shadow_zero_run,
                        limit=candidate_region[1],
                    )
                    if candidate_region is not None
                    else None
                )
                if tail is not None:
                    shadow = _shadow_match(
                        start=start,
                        end=end,
                        text=row["text"],
                        raw=raw,
                        regions=regions,
                        region_starts=region_starts,
                        dialogue_by_resource=dialogue_by_resource,
                        distance_limit=shadow_distance,
                        tail=tail,
                    )
            if shadow is not None:
                shadow_count += 1
                if rejected is not None:
                    rejected.writerow(
                        {
                            "bank": bank_for_offset(start),
                            "offset": row["offset"],
                            "sector": row["sector"],
                            "within_sector": row["within_sector"],
                            "bytes": row["bytes"],
                            "characters": row["characters"],
                            "text": row["text"],
                            "rejection_reason": "nearby_dialogue_fragment",
                            "resource_name": shadow.resource_name,
                            "matched_dialogue_offset": f"0x{shadow.dialogue_offset:08X}",
                            "distance_bytes": shadow.distance_bytes,
                            "tail_zero_bytes": shadow.tail_zero_bytes,
                            "dangling_lead_byte": (
                                f"0x{shadow.dangling_lead_byte:02X}"
                                if shadow.dangling_lead_byte is not None
                                else ""
                            ),
                        }
                    )
                continue

            writer.writerow(
                {
                    "bank": bank_for_offset(start),
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

    return AuxiliaryStats(
        count,
        len(unique_texts),
        character_count,
        overlap_count,
        shadow_count,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the auxiliary-text subtraction command parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Remove structured-dialogue overlaps and conservatively proven "
            "dialogue-shadow fragments from a likely Shift-JIS scan."
        )
    )
    parser.add_argument("likely_scan", type=pathlib.Path)
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--resource-map", type=pathlib.Path)
    parser.add_argument("--track", type=pathlib.Path)
    parser.add_argument("--rejected-output", type=pathlib.Path)
    parser.add_argument(
        "--shadow-distance",
        type=lambda value: int(value, 0),
        default=DEFAULT_SHADOW_DISTANCE,
        metavar="BYTES",
    )
    parser.add_argument(
        "--shadow-zero-run",
        type=int,
        default=DEFAULT_SHADOW_ZERO_RUN,
        metavar="BYTES",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run auxiliary extraction and print deterministic summary counters."""

    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.resource_map is None) != (args.track is None):
        parser.error("--resource-map and --track must be supplied together")
    if args.rejected_output is not None and args.track is None:
        parser.error("--rejected-output requires --resource-map and --track")
    try:
        if args.track is None:
            stats = write_auxiliary_text(
                args.likely_scan,
                args.dialogue,
                args.output,
                shadow_distance=args.shadow_distance,
                shadow_zero_run=args.shadow_zero_run,
            )
        else:
            with mapped_file(args.track) as data:
                stats = write_auxiliary_text(
                    args.likely_scan,
                    args.dialogue,
                    args.output,
                    resource_map=args.resource_map,
                    data=data,
                    rejected_output=args.rejected_output,
                    shadow_distance=args.shadow_distance,
                    shadow_zero_run=args.shadow_zero_run,
                )
    except ValueError as error:
        parser.error(str(error))
    print(f"records={stats.records}")
    print(f"unique_texts={stats.unique_texts}")
    print(f"characters={stats.characters}")
    print(f"dialogue_overlaps={stats.dialogue_overlaps}")
    print(f"dialogue_shadows={stats.dialogue_shadows}")
    return 0


__all__ = [
    "AuxiliaryStats",
    "DEFAULT_SHADOW_DISTANCE",
    "DEFAULT_SHADOW_ZERO_RUN",
    "OUTPUT_FIELDS",
    "REJECTION_FIELDS",
    "build_parser",
    "main",
    "merge_ranges",
    "parse_hex",
    "write_auxiliary_text",
]


if __name__ == "__main__":
    raise SystemExit(main())
