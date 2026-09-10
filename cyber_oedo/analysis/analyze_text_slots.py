#!/usr/bin/env python3
"""Measure dialogue tails inside header-bounded resource regions."""

from __future__ import annotations

import argparse
import bisect
import collections
import pathlib

import numpy as np
from collections.abc import Sequence

from cyber_oedo.disc.game_layout import (
    LIKELY_PADDING_BYTES,
    SECTOR_SIZE,
)
from cyber_oedo.io import mapped_file
from cyber_oedo.resources import ResourceHeader
from cyber_oedo.tabular import tsv_dict_reader, tsv_dict_writer

OUTPUT_FIELDS = (
    "resource_sector",
    "resource_name",
    "next_resource_sector",
    "bank",
    "region_sectors",
    "boundary_quality",
    "records",
    "records_crossing_region",
    "last_record_end_in_region",
    "tail_bytes",
    "tail_dominant_byte",
    "tail_dominant_ratio",
    "tail_is_likely_padding",
)


def parse_hex(value: str) -> int:
    """Parse a hexadecimal payload offset from an upstream TSV."""

    return int(value, 16)


def read_resource_headers(resource_map: pathlib.Path) -> list[ResourceHeader]:
    """Read canonical Tier-A resource candidates without rediscovering headers."""

    with tsv_dict_reader(resource_map) as reader:
        headers = [
            ResourceHeader(sector=int(row["resource_sector"]), name=row["resource_name"])
            for row in reader
        ]
    return sorted(headers)


def build_parser() -> argparse.ArgumentParser:
    """Build the heuristic resource-tail command parser."""

    return argparse.ArgumentParser(
        description=(
            "Measure candidate padding after dialogue records inside "
            "named, header-bounded resource regions."
        ),
        epilog=(
            "A 'yes' padding result is evidence for follow-up only. "
            "Never overwrite a tail until its references are mapped."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Analyze resource tails through a read-only mapped payload."""

    parser = build_parser()
    parser.add_argument(
        "track",
        type=pathlib.Path,
        help="Track 2 payload .bin",
    )
    parser.add_argument(
        "dialogue",
        type=pathlib.Path,
        help="TSV produced by extract_dialogue.py",
    )
    parser.add_argument(
        "resource_map",
        type=pathlib.Path,
        help="resource_map.tsv produced by build-resource-map or analyze",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination analysis TSV",
    )
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="include dialogue candidates flagged for review",
    )
    parser.add_argument(
        "--max-region-sectors",
        type=int,
        default=64,
        metavar="N",
        help=(
            "largest consecutive-header gap allowed to support a "
            "padding candidate (default: 64)"
        ),
    )
    args = parser.parse_args(argv)
    if args.max_region_sectors <= 0:
        parser.error("--max-region-sectors must be positive")

    headers = read_resource_headers(args.resource_map)
    if not headers:
        parser.error("no candidate sector-aligned resource headers were found")
    header_sectors = [header.sector for header in headers]

    grouped: dict[
        int,
        list[tuple[str, int, int]],
    ] = collections.defaultdict(list)
    unassigned_records = 0
    with tsv_dict_reader(args.dialogue) as reader:
        for row in reader:
            if not args.include_review and row["quality"] != "likely_text":
                continue
            record_offset = parse_hex(row["offset"])
            record_sector = record_offset // SECTOR_SIZE
            header_index = (
                bisect.bisect_right(
                    header_sectors,
                    record_sector,
                )
                - 1
            )
            if header_index < 0:
                unassigned_records += 1
                continue
            grouped[header_index].append(
                (
                    row["bank"],
                    record_offset,
                    int(row["record_bytes"]),
                )
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    text_regions = 0
    bounded_regions = 0
    crossing_total = 0
    padded_count = 0
    tail_sizes: list[int] = []

    with (
        mapped_file(args.track) as data,
        tsv_dict_writer(args.output, OUTPUT_FIELDS) as writer,
    ):
        sector_count, remainder = divmod(len(data), SECTOR_SIZE)
        if remainder:
            parser.error(
                "track length is not aligned to "
                f"{SECTOR_SIZE}-byte sectors "
                f"(remainder: {remainder})"
            )
        for header_index in sorted(grouped):
            region_records = grouped[header_index]
            header = headers[header_index]
            next_sector = (
                headers[header_index + 1].sector
                if header_index + 1 < len(headers)
                else sector_count
            )
            region_start = header.sector * SECTOR_SIZE
            region_end = min(
                next_sector * SECTOR_SIZE,
                len(data),
            )
            record_ends = [
                offset + byte_count for _, offset, byte_count in region_records
            ]
            crossing = sum(record_end > region_end for record_end in record_ends)
            last_record_end = max(record_ends)
            tail_start = min(
                max(last_record_end, region_start),
                region_end,
            )
            tail_bytes = region_end - tail_start
            if tail_bytes:
                tail = np.frombuffer(
                    data,
                    dtype=np.uint8,
                    count=tail_bytes,
                    offset=tail_start,
                )
                counts = np.bincount(tail, minlength=256)
                fill_byte = int(counts.argmax())
                fill_count = int(counts[fill_byte])
                fill_ratio = fill_count / tail_bytes
                del tail
            else:
                fill_byte, fill_ratio = 0, 0.0
            region_sectors = next_sector - header.sector
            bounded = region_sectors <= args.max_region_sectors
            boundary_quality = (
                "adjacent_named_headers" if bounded else "wide_header_gap"
            )
            likely_padding = (
                bounded and fill_byte in LIKELY_PADDING_BYTES and fill_ratio >= 0.80
            )
            writer.writerow(
                {
                    "resource_sector": header.sector,
                    "resource_name": header.name,
                    "next_resource_sector": next_sector,
                    "bank": region_records[0][0],
                    "region_sectors": region_sectors,
                    "boundary_quality": boundary_quality,
                    "records": len(region_records),
                    "records_crossing_region": crossing,
                    "last_record_end_in_region": (last_record_end - region_start),
                    "tail_bytes": tail_bytes,
                    "tail_dominant_byte": f"{fill_byte:02X}",
                    "tail_dominant_ratio": f"{fill_ratio:.5f}",
                    "tail_is_likely_padding": ("yes" if likely_padding else "no"),
                }
            )
            text_regions += 1
            crossing_total += crossing
            if bounded:
                bounded_regions += 1
                tail_sizes.append(tail_bytes)
            if likely_padding:
                padded_count += 1

    tail_sizes.sort()
    print(f"resource_headers={len(headers)}")
    print(f"text_regions={text_regions}")
    print(f"unassigned_records={unassigned_records}")
    print(f"bounded_text_regions={bounded_regions}")
    print(f"wide_header_gaps={text_regions - bounded_regions}")
    print(f"records_crossing_regions={crossing_total}")
    print(f"likely_padded_tails={padded_count}")
    if tail_sizes:
        print(f"median_tail_bytes={tail_sizes[len(tail_sizes) // 2]}")
        print(f"max_tail_bytes={tail_sizes[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
