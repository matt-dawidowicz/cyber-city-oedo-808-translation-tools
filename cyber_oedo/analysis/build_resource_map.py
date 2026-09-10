#!/usr/bin/env python3
"""Build a complete sector-aligned candidate resource map for Track 2."""

from __future__ import annotations

import argparse
import csv
import pathlib
from collections import Counter
from collections.abc import Sequence

from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file
from cyber_oedo.resources import (
    build_candidate_regions,
    discover_resource_headers,
)

OUTPUT_FIELDS = (
    "resource_sector",
    "resource_offset",
    "resource_name",
    "end_sector_exclusive",
    "end_offset_exclusive",
    "sector_count",
    "byte_count",
    "bank",
    "boundary_source",
    "ownership_status",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the candidate-resource mapping command parser."""

    return argparse.ArgumentParser(
        description=(
            "Discover every plausible sector-aligned resource header and "
            "bound it by the next candidate header or Track 2 end."
        ),
        epilog=(
            "Candidate regions are structural evidence only. They do not "
            "establish loader extent, writable padding, or free space."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Scan the payload directly and write every candidate resource region."""

    parser = build_parser()
    parser.add_argument(
        "track",
        type=pathlib.Path,
        help="Track 2 payload .bin",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination candidate resource-map TSV",
    )
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with mapped_file(args.track) as data:
        sector_count, remainder = divmod(len(data), SECTOR_SIZE)
        if remainder:
            parser.error(f"track length is not aligned to {SECTOR_SIZE}-byte sectors")
        headers = discover_resource_headers(data)
        regions = build_candidate_regions(headers, sector_count)

    with args.output.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=OUTPUT_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        for region in regions:
            writer.writerow(
                {
                    "resource_sector": region.start_sector,
                    "resource_offset": (f"0x{region.start_offset:08X}"),
                    "resource_name": region.header.name,
                    "end_sector_exclusive": region.end_sector,
                    "end_offset_exclusive": (f"0x{region.end_offset:08X}"),
                    "sector_count": region.sector_count,
                    "byte_count": region.byte_count,
                    "bank": region.bank,
                    "boundary_source": region.boundary_source,
                    "ownership_status": "unproven",
                }
            )

    banks = Counter(region.bank for region in regions)
    print(f"candidate_headers={len(headers)}")
    print(f"candidate_regions={len(regions)}")
    for bank in sorted(banks):
        print(f"{bank}={banks[bank]}")
    return 0


__all__ = ["OUTPUT_FIELDS", "build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
