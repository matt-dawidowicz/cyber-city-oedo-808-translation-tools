#!/usr/bin/env python3
"""Build a complete sector-aligned candidate resource map for Track 2."""

from __future__ import annotations

import argparse
import pathlib
from collections import Counter
from collections.abc import Sequence

from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file
from cyber_oedo.resources import build_candidate_regions, discover_resource_headers
from cyber_oedo.tabular import tsv_dict_writer

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


def write_resource_map(data: object, output_path: pathlib.Path) -> tuple[int, int, Counter[str]]:
    """Discover canonical resource candidates from one existing payload map."""

    sector_count, remainder = divmod(len(data), SECTOR_SIZE)  # type: ignore[arg-type]
    if remainder:
        raise ValueError(f"track length is not aligned to {SECTOR_SIZE}-byte sectors")
    headers = discover_resource_headers(data)
    regions = build_candidate_regions(headers, sector_count)
    with tsv_dict_writer(output_path, OUTPUT_FIELDS) as writer:
        for region in regions:
            writer.writerow(
                {
                    "resource_sector": region.start_sector,
                    "resource_offset": f"0x{region.start_offset:08X}",
                    "resource_name": region.header.name,
                    "end_sector_exclusive": region.end_sector,
                    "end_offset_exclusive": f"0x{region.end_offset:08X}",
                    "sector_count": region.sector_count,
                    "byte_count": region.byte_count,
                    "bank": region.bank,
                    "boundary_source": region.boundary_source,
                    "ownership_status": "unproven",
                }
            )
    return len(headers), len(regions), Counter(region.bank for region in regions)


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
    parser.add_argument("track", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument("output", type=pathlib.Path, help="destination candidate resource-map TSV")
    args = parser.parse_args(argv)
    try:
        with mapped_file(args.track) as data:
            header_count, region_count, banks = write_resource_map(data, args.output)
    except ValueError as error:
        parser.error(str(error))

    print(f"candidate_headers={header_count}")
    print(f"candidate_regions={region_count}")
    for bank in sorted(banks):
        print(f"{bank}={banks[bank]}")
    return 0


__all__ = ["OUTPUT_FIELDS", "build_parser", "main", "write_resource_map"]


if __name__ == "__main__":
    raise SystemExit(main())
