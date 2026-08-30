#!/usr/bin/env python3
"""Measure text tails inside header-bounded resource regions.

The filename is retained for compatibility with the initial analysis, but the
implementation no longer assumes globally aligned four-sector "slots".  That
assumption was disproved: named resources commonly begin four sectors apart,
yet some span eight, twelve, or more sectors, and alignment changes by mission.

Instead, this tool discovers candidate resource headers from
``ascii_strings.tsv``.  A header must:

* begin at offset zero of a 2048-byte payload sector;
* consist of 2-16 uppercase ASCII letters, digits, or underscores; and
* not be a repeated single fill character.

Each region runs from one header sector to the next.  Dialogue records are
assigned to the closest preceding header, and the bytes after the last record
are summarized.  This is still a heuristic: a constant-fill tail is useful
relocation evidence, but it is never proof that bytes are unreferenced or safe
to overwrite.  Pointer/length analysis and runtime validation remain required.

Inputs are the extracted payload, structured dialogue TSV, and ASCII scan TSV.
Output is a heuristic region-summary TSV. The command reads the payload into
memory, creates the destination directory, replaces the requested output, and
prints aggregate diagnostics. It never modifies source files.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import csv
import pathlib
import re
from dataclasses import dataclass

from game_layout import LIKELY_PADDING_BYTES, SECTOR_SIZE


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
    """Represent a candidate named resource at a sector boundary.

    Attributes:
        sector: Relative 2048-byte payload sector containing the name at byte
            offset zero.
        name: Uppercase ASCII candidate retained by the header heuristic.

    Notes:
        A ``ResourceHeader`` records discovery evidence only. It does not prove
        that the name begins a complete, independently relocatable resource.
    """

    sector: int
    name: str


def parse_hex(value: str) -> int:
    """Parse a hexadecimal payload offset from an upstream TSV.

    Args:
        value: String accepted by ``int(value, 16)``, normally ``0x...``.

    Returns:
        The corresponding integer payload offset.

    Raises:
        ValueError: If ``value`` is not valid hexadecimal.
        TypeError: If ``value`` is not a string-like value accepted by
            ``int``.
    """

    return int(value, 16)


def looks_like_resource_name(text: str) -> bool:
    """Return whether an ASCII run resembles a resource name.

    Args:
        text: Decoded ASCII run beginning at a sector boundary.

    Returns:
        ``True`` for a 2-16 character uppercase name containing letters,
        digits, or underscores, unless a name of four or more characters
        repeats only one fill character.

    Design Decisions:
        Short names such as ``AF01`` and mixed names such as ``GATE1`` are
        retained. Long runs such as ``UUUUUUUU`` are rejected because they
        commonly represent fill rather than identifiers.
    """

    if RESOURCE_NAME.fullmatch(text) is None:
        return False
    # Repeated long runs usually represent sector fill. Short legitimate names
    # and identifiers containing more than one distinct character are kept.
    return len(text) < 4 or len(set(text)) > 1


def read_resource_headers(ascii_scan: pathlib.Path) -> list[ResourceHeader]:
    """Read sector-aligned resource-name candidates from an ASCII scan.

    Args:
        ascii_scan: ``ascii_strings.tsv`` produced by ``scan_track.py``.

    Returns:
        Candidate headers sorted by relative payload sector.

    Raises:
        OSError: If the TSV cannot be opened or read.
        csv.Error: If quoted TSV data is malformed.
        KeyError: If required columns are absent.
        ValueError: If a retained ``sector`` value is not an integer.

    Design Decisions:
        Only rows at ``within_sector == "0x000"`` are considered. If multiple
        candidates claim one sector, the final row wins; the normal upstream
        scanner emits at most one contiguous ASCII run from that byte offset.
    """

    by_sector: dict[int, str] = {}
    with ascii_scan.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            if row["within_sector"] != "0x000":
                continue
            text = row["text"]
            if looks_like_resource_name(text):
                by_sector[int(row["sector"])] = text
    return [
        ResourceHeader(sector=sector, name=name)
        for sector, name in sorted(by_sector.items())
    ]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser describing heuristic region analysis and its safety boundary.
        Input, output, and threshold arguments are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Measure candidate padding after dialogue records inside named, "
            "header-bounded resource regions."
        ),
        epilog=(
            "A 'yes' padding result is evidence for follow-up only. Never "
            "overwrite or relocate into a tail until its references are "
            "mapped."
        ),
    )


def main() -> None:
    """Analyze dialogue tails within candidate named-resource regions.

    Inputs:
        Parses payload, dialogue TSV, ASCII-scan TSV, output TSV, confidence
        inclusion, and maximum region-gap arguments from the command line.

    Outputs:
        Writes one summary row per discovered region containing selected
        dialogue records. Prints header, region, boundary, crossing, and
        candidate-padding statistics.

    Side Effects:
        Reads the full payload and both TSV inputs, creates the output parent
        directory, and replaces the output TSV.

    Failure Conditions:
        ``argparse`` exits for a non-positive maximum gap, a payload not
        aligned to 2048-byte sectors, or no candidate headers. File-system,
        CSV, missing-column, and malformed-number errors otherwise propagate.

    Design Decisions:
        The next sector-aligned name bounds a candidate region. Gaps larger
        than the configured threshold are labeled ``wide_header_gap`` and
        cannot be reported as likely padding. Dominant fill still provides
        evidence, but no output row grants permission to overwrite bytes.
    """

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
        "ascii_scan",
        type=pathlib.Path,
        help="ascii_strings.tsv produced by scan_track.py",
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
            "largest consecutive-header gap allowed to support a padding "
            "candidate (default: 64)"
        ),
    )
    args = parser.parse_args()
    if args.max_region_sectors <= 0:
        parser.error("--max-region-sectors must be positive")

    data = args.track.read_bytes()
    sector_count, remainder = divmod(len(data), SECTOR_SIZE)
    if remainder:
        parser.error(
            f"track length is not aligned to {SECTOR_SIZE}-byte sectors "
            f"(remainder: {remainder})"
        )

    headers = read_resource_headers(args.ascii_scan)
    if not headers:
        parser.error("no candidate sector-aligned resource headers were found")
    header_sectors = [header.sector for header in headers]

    with args.dialogue.open("r", encoding="utf-8-sig", newline="") as source:
        records = [
            row
            for row in csv.DictReader(source, delimiter="\t")
            if args.include_review or row["quality"] == "likely_text"
        ]

    grouped: dict[int, list[dict[str, str]]] = collections.defaultdict(list)
    unassigned_records = 0
    for row in records:
        record_offset = parse_hex(row["offset"])
        record_sector = record_offset // SECTOR_SIZE
        header_index = bisect.bisect_right(header_sectors, record_sector) - 1
        if header_index < 0:
            unassigned_records += 1
            continue
        grouped[header_index].append(row)

    rows: list[dict[str, object]] = []
    for header_index, region_records in sorted(grouped.items()):
        header = headers[header_index]
        next_sector = (
            headers[header_index + 1].sector
            if header_index + 1 < len(headers)
            else sector_count
        )
        region_start = header.sector * SECTOR_SIZE
        region_end = min(next_sector * SECTOR_SIZE, len(data))
        record_ends = [
            parse_hex(row["offset"]) + int(row["record_bytes"])
            for row in region_records
        ]
        crossing = sum(record_end > region_end for record_end in record_ends)
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
                "tail_is_likely_padding": (
                    "yes"
                    if (
                        boundary_quality == "adjacent_named_headers"
                        and fill_byte in LIKELY_PADDING_BYTES
                        and fill_ratio >= 0.80
                    )
                    else "no"
                ),
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

    padded = [row for row in rows if row["tail_is_likely_padding"] == "yes"]
    bounded_rows = [
        row
        for row in rows
        if row["boundary_quality"] == "adjacent_named_headers"
    ]
    tail_sizes = sorted(int(row["tail_bytes"]) for row in bounded_rows)
    print(f"resource_headers={len(headers)}")
    print(f"text_regions={len(rows)}")
    print(f"unassigned_records={unassigned_records}")
    print(f"bounded_text_regions={len(bounded_rows)}")
    print(f"wide_header_gaps={len(rows) - len(bounded_rows)}")
    print(
        "records_crossing_regions="
        f"{sum(int(row['records_crossing_region']) for row in rows)}"
    )
    print(f"likely_padded_tails={len(padded)}")
    if tail_sizes:
        print(f"median_tail_bytes={tail_sizes[len(tail_sizes) // 2]}")
        print(f"max_tail_bytes={tail_sizes[-1]}")


if __name__ == "__main__":
    main()
