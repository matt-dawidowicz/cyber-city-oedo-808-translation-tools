#!/usr/bin/env python3
"""Create a structural inventory of Track 2 with native hot-path scans."""

from __future__ import annotations

import argparse
import collections
import math
import pathlib
import re
from collections.abc import Iterator, Mapping, Sequence

from cyber_oedo.analysis.fast_scan import broad_sjis_runs, sector_metrics
from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file, sha256_buffer


def _entropy_from_counts(
    counts: Mapping[int, int],
    length: int,
) -> float:
    """Return Shannon entropy from one existing byte-frequency table."""

    if length <= 0:
        return 0.0
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def entropy(data: bytes) -> float:
    """Calculate Shannon entropy in bits per byte."""

    if not data:
        return 0.0
    return _entropy_from_counts(
        collections.Counter(data),
        len(data),
    )


def zero_runs(flags: Sequence[bool]) -> list[tuple[int, int]]:
    """Convert Boolean sector flags into half-open zero-sector runs."""

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_zero in enumerate(flags):
        if is_zero and start is None:
            start = index
        elif not is_zero and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


def scan_ascii(
    data: object,
    minimum: int = 4,
) -> Iterator[tuple[int, str]]:
    """Yield contiguous printable ASCII runs."""

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    for match in pattern.finditer(data):  # type: ignore[arg-type]
        yield match.start(), match.group().decode("ascii")


def scan_shift_jis(
    data: object,
    minimum_japanese: int = 3,
) -> Iterator[tuple[int, int, str]]:
    """Yield broad Shift-JIS runs using the compiled token state machine."""

    starts, ends, japanese_counts = broad_sjis_runs(
        data,
        minimum_japanese,
    )
    for start, end, japanese in zip(
        starts,
        ends,
        japanese_counts,
        strict=True,
    ):
        offset = int(start)
        raw = data[offset:int(end)]  # type: ignore[index]
        try:
            decoded = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        yield (
            offset,
            int(japanese),
            decoded.replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t"),
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the broad structural reconnaissance command parser."""

    return argparse.ArgumentParser(
        description=(
            "Inventory sector structure, ASCII labels, and broad "
            "Shift-JIS runs in the extracted Track 2 payload."
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Generate reports without copying or buffering the full payload."""

    parser = build_parser()
    parser.add_argument(
        "track",
        type=pathlib.Path,
        help="Track 2 payload .bin",
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        required=True,
    )
    parser.add_argument(
        "--minimum-ascii",
        type=int,
        default=4,
        metavar="N",
    )
    parser.add_argument(
        "--minimum-japanese",
        type=int,
        default=3,
        metavar="N",
    )
    args = parser.parse_args(argv)
    if args.minimum_ascii <= 0:
        parser.error("--minimum-ascii must be positive")
    if args.minimum_japanese <= 0:
        parser.error("--minimum-japanese must be positive")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    with mapped_file(args.track) as data:
        byte_count = len(data)
        sector_count, remainder = divmod(
            byte_count,
            SECTOR_SIZE,
        )
        if remainder:
            raise SystemExit(
                "Track length is not sector-aligned: "
                f"remainder {remainder}"
            )

        nonzero, unique, entropy_values, zero_flags_array = sector_metrics(
            data,
            SECTOR_SIZE,
        )
        zero_flags = zero_flags_array.tolist()
        sector_map = output_dir / "sector_map.tsv"
        with sector_map.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as output:
            output.write(
                "sector\toffset\tnonzero\tunique\tentropy\t"
                "prefix_hex\n"
            )
            for sector_number in range(sector_count):
                start = sector_number * SECTOR_SIZE
                prefix = data[start:start + 16]  # type: ignore[index]
                output.write(
                    f"{sector_number}\t0x{start:08X}\t"
                    f"{int(nonzero[sector_number])}\t"
                    f"{int(unique[sector_number])}\t"
                    f"{float(entropy_values[sector_number]):.5f}\t"
                    f"{prefix.hex(' ')}\n"
                )

        ascii_count = 0
        ascii_path = output_dir / "ascii_strings.tsv"
        with ascii_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as output:
            output.write(
                "offset\tsector\twithin_sector\ttext\n"
            )
            for offset, text in scan_ascii(
                data,
                args.minimum_ascii,
            ):
                escaped = text.replace(
                    "\\",
                    "\\\\",
                ).replace("\t", "\\t")
                output.write(
                    f"0x{offset:08X}\t"
                    f"{offset // SECTOR_SIZE}\t"
                    f"0x{offset % SECTOR_SIZE:03X}\t"
                    f"{escaped}\n"
                )
                ascii_count += 1

        sjis_count = 0
        sjis_path = output_dir / "shift_jis_strings.tsv"
        with sjis_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as output:
            output.write(
                "offset\tsector\twithin_sector\t"
                "japanese_chars\ttext\n"
            )
            for offset, japanese, text in scan_shift_jis(
                data,
                args.minimum_japanese,
            ):
                escaped = text.replace(
                    "\\",
                    "\\\\",
                ).replace("\t", "\\t")
                output.write(
                    f"0x{offset:08X}\t"
                    f"{offset // SECTOR_SIZE}\t"
                    f"0x{offset % SECTOR_SIZE:03X}\t"
                    f"{japanese}\t{escaped}\n"
                )
                sjis_count += 1

        runs = zero_runs(zero_flags)
        zero_count = int(zero_flags_array.sum())
        digest = sha256_buffer(data)

    summary = [
        f"path={args.track.resolve()}",
        f"bytes={byte_count}",
        f"sectors={sector_count}",
        f"sha256={digest}",
        f"zero_sectors={zero_count}",
        f"nonzero_sectors={sector_count - zero_count}",
        f"zero_runs={len(runs)}",
        f"ascii_runs={ascii_count}",
        f"shift_jis_runs={sjis_count}",
        "",
        (
            "long_zero_sector_runs "
            "(start inclusive, end exclusive, count):"
        ),
    ]
    summary.extend(
        f"{start}\t{end}\t{end - start}"
        for start, end in runs
        if end - start >= 2
    )
    (output_dir / "summary.txt").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
