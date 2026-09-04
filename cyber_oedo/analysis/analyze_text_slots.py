"""Measure dialogue tails inside header-bounded resource regions."""

from __future__ import annotations

import argparse
import bisect
import collections
import csv
import pathlib
import re
from dataclasses import dataclass

from cyber_oedo.disc.game_layout import LIKELY_PADDING_BYTES, SECTOR_SIZE

RESOURCE_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,15}$")
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


@dataclass(frozen=True, slots=True)
class ResourceHeader:
    """Represent a candidate sector-aligned resource name."""

    sector: int
    name: str


def parse_hex(value: str) -> int:
    """Parse a hexadecimal payload offset."""

    return int(value, 16)


def looks_like_resource_name(text: str) -> bool:
    """Return whether an ASCII run resembles a resource name."""

    if RESOURCE_NAME.fullmatch(text) is None:
        return False
    return len(text) < 4 or len(set(text)) > 1


def read_resource_headers(path: pathlib.Path) -> list[ResourceHeader]:
    """Read sector-aligned resource-name candidates from an ASCII scan."""

    by_sector: dict[int, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            if row["within_sector"] != "0x000":
                continue
            if looks_like_resource_name(row["text"]):
                by_sector[int(row["sector"])] = row["text"]
    return [
        ResourceHeader(sector=sector, name=name)
        for sector, name in sorted(by_sector.items())
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the resource-tail analysis parser."""

    parser = argparse.ArgumentParser(
        description="Measure candidate fill tails inside named resource regions."
    )
    parser.add_argument("track", type=pathlib.Path)
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("ascii_scan", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--include-review", action="store_true")
    parser.add_argument("--max-region-sectors", type=int, default=64)
    return parser


def main() -> None:
    """Write heuristic resource-tail measurements without authorizing writes."""

    parser = build_parser()
    args = parser.parse_args()
    if args.max_region_sectors <= 0:
        parser.error("--max-region-sectors must be positive")

    data = args.track.read_bytes()
    sector_count, remainder = divmod(len(data), SECTOR_SIZE)
    if remainder:
        parser.error("track length is not sector-aligned")

    headers = read_resource_headers(args.ascii_scan)
    if not headers:
        parser.error("no sector-aligned resource headers found")
    header_sectors = [header.sector for header in headers]

    with args.dialogue.open("r", encoding="utf-8-sig", newline="") as source:
        records = [
            row
            for row in csv.DictReader(source, delimiter="\t")
            if args.include_review or row["quality"] == "likely_text"
        ]

    grouped: dict[int, list[dict[str, str]]] = collections.defaultdict(list)
    for row in records:
        sector = parse_hex(row["offset"]) // SECTOR_SIZE
        index = bisect.bisect_right(header_sectors, sector) - 1
        if index >= 0:
            grouped[index].append(row)

    rows: list[dict[str, object]] = []
    for index, region_records in sorted(grouped.items()):
        header = headers[index]
        next_sector = (
            headers[index + 1].sector
            if index + 1 < len(headers)
            else sector_count
        )
        region_start = header.sector * SECTOR_SIZE
        region_end = min(next_sector * SECTOR_SIZE, len(data))
        record_ends = [
            parse_hex(row["offset"]) + int(row["record_bytes"])
            for row in region_records
        ]
        crossing = sum(end > region_end for end in record_ends)
        last_record_end = max(record_ends)
        tail_start = min(max(last_record_end, region_start), region_end)
        tail = data[tail_start:region_end]
        if tail:
            fill_byte, fill_count = collections.Counter(tail).most_common(1)[0]
            fill_ratio = fill_count / len(tail)
        else:
            fill_byte, fill_ratio = 0, 0.0

        region_sectors = next_sector - header.sector
        boundary_quality = (
            "adjacent_named_headers"
            if region_sectors <= args.max_region_sectors
            else "wide_header_gap"
        )
        likely_padding = (
            boundary_quality == "adjacent_named_headers"
            and fill_byte in LIKELY_PADDING_BYTES
            and fill_ratio >= 0.80
        )
        rows.append(
            {
                "resource_sector": header.sector,
                "resource_name": header.name,
                "next_resource_sector": next_sector,
                "bank": region_records[0]["bank"],
                "region_sectors": region_sectors,
                "boundary_quality": boundary_quality,
                "records": len(region_records),
                "records_crossing_region": crossing,
                "last_record_end_in_region": last_record_end - region_start,
                "tail_bytes": len(tail),
                "tail_dominant_byte": f"{fill_byte:02X}",
                "tail_dominant_ratio": f"{fill_ratio:.5f}",
                "tail_is_likely_padding": "yes" if likely_padding else "no",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=OUTPUT_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"resource_headers={len(headers)}")
    print(f"text_regions={len(rows)}")
    print(
        "likely_padded_tails="
        f"{sum(row['tail_is_likely_padding'] == 'yes' for row in rows)}"
    )


if __name__ == "__main__":
    main()
