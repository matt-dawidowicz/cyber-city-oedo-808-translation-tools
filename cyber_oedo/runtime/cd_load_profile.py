"""Analyze Mesen CD_READ traces and identify load-time optimization targets.

The profiler consumes the project's read-only Mesen logs instead of guessing
from disc layout.  It reports exact repeated read signatures, load-burst timing,
and the amount of data that is retransferred during the captured route.

This module does not claim that repeated reads are automatically removable:
RAM/VRAM destinations may have been overwritten between reads.  Repetition is
an optimization target that still requires lifetime/ownership proof.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
from dataclasses import asdict, dataclass
from typing import Iterable

SECTOR_BYTES = 2048
CD_SECTORS_PER_SECOND = 75
TRACK2_START_LBA = 3590

_CD_READ_RE = re.compile(
    r"\[CD_READ\s+(?P<ordinal>\d+)\s+B(?P<burst>\d+)\]\s+"
    r"frame=(?P<frame>\d+)\s+"
    r"sector=\$(?P<sector>[0-9A-Fa-f]+).*?"
    r"type=\$(?P<type>[0-9A-Fa-f]+)\([^)]*\)\s+"
    r"dest=\$(?P<dest>[0-9A-Fa-f]+)\s+"
    r"len=\$(?P<length>[0-9A-Fa-f]+)_(?P<unit>bytes|sectors)"
)


@dataclass(frozen=True, slots=True)
class CdRead:
    ordinal: int
    burst: int
    frame: int
    sector: int
    address_type: int
    destination: int
    length: int
    unit: str

    @property
    def transfer_bytes(self) -> int:
        return self.length * SECTOR_BYTES if self.unit == "sectors" else self.length

    @property
    def transfer_sectors(self) -> int:
        return math.ceil(self.transfer_bytes / SECTOR_BYTES)

    @property
    def signature(self) -> tuple[int, int, int, int, str]:
        return (
            self.sector,
            self.address_type,
            self.destination,
            self.length,
            self.unit,
        )

    @property
    def source_end_sector(self) -> int:
        return self.sector + self.transfer_sectors


@dataclass(frozen=True, slots=True)
class LoadBurst:
    burst: int
    first_frame: int
    last_frame: int
    reads: tuple[CdRead, ...]

    @property
    def frame_span(self) -> int:
        return self.last_frame - self.first_frame

    @property
    def transfer_bytes(self) -> int:
        return sum(item.transfer_bytes for item in self.reads)

    @property
    def signatures(self) -> tuple[tuple[int, int, int, int, str], ...]:
        return tuple(item.signature for item in self.reads)


def parse_cd_read_log(text: str) -> tuple[CdRead, ...]:
    """Parse the stable CD_READ lines emitted by the Mesen capture scripts."""

    rows: list[CdRead] = []
    for line in text.splitlines():
        match = _CD_READ_RE.search(line)
        if match is None:
            continue
        address_type = int(match.group("type"), 16)
        length = int(match.group("length"), 16)
        unit = match.group("unit")

        # Historical V5 logging read F8/F9 as one 16-bit value.  For local
        # sector requests F9 also held address type 01, so e.g. 0105 meant five
        # sectors.  Normalize that known logger artifact while retaining strict
        # behavior for every other request type.
        if address_type == 0x01 and unit == "sectors" and length > 0xFF:
            if length >> 8 != address_type:
                raise ValueError(
                    "unexpected high byte in historical local-sector length: "
                    f"0x{length:04X}"
                )
            length &= 0xFF

        rows.append(
            CdRead(
                ordinal=int(match.group("ordinal")),
                burst=int(match.group("burst")),
                frame=int(match.group("frame")),
                sector=int(match.group("sector"), 16),
                address_type=address_type,
                destination=int(match.group("dest"), 16),
                length=length,
                unit=unit,
            )
        )
    return tuple(rows)


def group_bursts(reads: Iterable[CdRead]) -> tuple[LoadBurst, ...]:
    grouped: dict[int, list[CdRead]] = collections.defaultdict(list)
    for item in reads:
        grouped[item.burst].append(item)
    return tuple(
        LoadBurst(
            burst=burst,
            first_frame=items[0].frame,
            last_frame=items[-1].frame,
            reads=tuple(items),
        )
        for burst, items in sorted(grouped.items())
    )


def _signature_row(signature: tuple[int, int, int, int, str]) -> dict[str, object]:
    sector, address_type, destination, length, unit = signature
    byte_count = length * SECTOR_BYTES if unit == "sectors" else length
    relative_sector = sector - TRACK2_START_LBA
    return {
        "absolute_lba": f"0x{sector:06X}",
        "track2_relative_sector": (
            f"0x{relative_sector:04X}" if relative_sector >= 0 else None
        ),
        "track2_payload_offset": (
            f"0x{relative_sector * SECTOR_BYTES:08X}"
            if relative_sector >= 0
            else None
        ),
        "address_type": f"0x{address_type:02X}",
        "destination": f"0x{destination:04X}",
        "length": length,
        "unit": unit,
        "transfer_bytes": byte_count,
        "transfer_sectors": math.ceil(byte_count / SECTOR_BYTES),
    }


def build_cd_load_report(text: str) -> dict[str, object]:
    reads = parse_cd_read_log(text)
    if not reads:
        raise ValueError("no CD_READ records were found")

    counts = collections.Counter(item.signature for item in reads)
    first_by_signature = {item.signature: item for item in reads}
    total_bytes = sum(item.transfer_bytes for item in reads)
    unique_signature_bytes = sum(
        first_by_signature[signature].transfer_bytes for signature in counts
    )
    repeated_extra_bytes = sum(
        (count - 1) * first_by_signature[signature].transfer_bytes
        for signature, count in counts.items()
    )

    bursts = group_bursts(reads)
    bundle_counts = collections.Counter(burst.signatures for burst in bursts)

    repeated = []
    for signature, count in sorted(
        counts.items(),
        key=lambda item: (
            -((item[1] - 1) * first_by_signature[item[0]].transfer_bytes),
            item[0],
        ),
    ):
        if count < 2:
            continue
        row = _signature_row(signature)
        row.update(
            {
                "count": count,
                "repeat_extra_bytes": (
                    count - 1
                )
                * first_by_signature[signature].transfer_bytes,
            }
        )
        repeated.append(row)

    repeated_bundles = []
    for signatures, count in sorted(
        bundle_counts.items(),
        key=lambda item: (-item[1], item[0]),
    ):
        if count < 2:
            continue
        matching = [burst for burst in bursts if burst.signatures == signatures]
        repeated_bundles.append(
            {
                "count": count,
                "reads_per_bundle": len(signatures),
                "transfer_bytes_per_bundle": matching[0].transfer_bytes,
                "observed_frame_spans": [item.frame_span for item in matching],
                "reads": [_signature_row(item) for item in signatures],
            }
        )

    return {
        "read_count": len(reads),
        "burst_count": len(bursts),
        "total_transfer_bytes": total_bytes,
        "unique_signature_bytes": unique_signature_bytes,
        "repeat_extra_bytes": repeated_extra_bytes,
        "repeat_extra_percent_of_transfer": (
            repeated_extra_bytes / total_bytes * 100.0
        ),
        "minimum_streaming_seconds_at_1x": (
            sum(item.transfer_sectors for item in reads) / CD_SECTORS_PER_SECOND
        ),
        "repeated_reads": repeated,
        "repeated_bundles": repeated_bundles,
        "bursts": [
            {
                "burst": burst.burst,
                "first_frame": burst.first_frame,
                "last_frame": burst.last_frame,
                "frame_span": burst.frame_span,
                "read_count": len(burst.reads),
                "transfer_bytes": burst.transfer_bytes,
                "reads": [_signature_row(item.signature) for item in burst.reads],
            }
            for burst in bursts
        ],
        "caveat": (
            "Repeated signatures are optimization candidates, not proof that a "
            "read may be skipped. Destination lifetime and intervening writes "
            "must be proven first."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze Cyber City Oedo 808 Mesen CD_READ traces."
    )
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_cd_load_report(args.log.read_text(encoding="utf-8", errors="replace"))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
