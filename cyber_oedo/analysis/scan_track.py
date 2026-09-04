"""Create structural reconnaissance reports for an extracted payload."""

from __future__ import annotations

import argparse
import collections
import hashlib
import math
import pathlib
import re
from collections.abc import Iterator

from cyber_oedo.disc.game_layout import SECTOR_SIZE


def sha256(path: pathlib.Path) -> str:
    """Return a file's SHA-256 digest."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy(data: bytes) -> float:
    """Calculate Shannon entropy in bits per byte."""

    if not data:
        return 0.0
    counts = collections.Counter(data)
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def zero_runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Convert Boolean sector flags into half-open true runs."""

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_zero in enumerate(flags + [False]):
        if is_zero and start is None:
            start = index
        elif not is_zero and start is not None:
            runs.append((start, index))
            start = None
    return runs


def scan_ascii(data: bytes, minimum: int = 4) -> Iterator[tuple[int, str]]:
    """Yield contiguous printable ASCII runs."""

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    for match in pattern.finditer(data):
        yield match.start(), match.group().decode("ascii")


def scan_shift_jis(
    data: bytes,
    minimum_japanese: int = 3,
) -> Iterator[tuple[int, int, str]]:
    """Yield broad Shift-JIS-compatible runs with enough Japanese tokens."""

    if minimum_japanese <= 0:
        raise ValueError("minimum_japanese must be positive")
    offset = 0
    while offset < len(data):
        start = offset
        japanese = 0
        while offset < len(data):
            first = data[offset]
            if 0x20 <= first <= 0x7E or first in (0x09, 0x0A, 0x0D):
                offset += 1
            elif 0xA1 <= first <= 0xDF:
                japanese += 1
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < len(data)
                and (
                    0x40 <= data[offset + 1] <= 0x7E
                    or 0x80 <= data[offset + 1] <= 0xFC
                )
            ):
                japanese += 1
                offset += 2
            else:
                break
        if japanese >= minimum_japanese and offset > start:
            try:
                decoded = data[start:offset].decode("shift_jis")
            except UnicodeDecodeError:
                decoded = ""
            if decoded:
                yield start, japanese, decoded
        offset = max(offset + 1, start + 1)


def build_parser() -> argparse.ArgumentParser:
    """Build the structural scanner argument parser."""

    parser = argparse.ArgumentParser(
        description="Inventory sectors, ASCII labels, and broad Shift-JIS runs."
    )
    parser.add_argument("track", type=pathlib.Path)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--minimum-ascii", type=int, default=4)
    parser.add_argument("--minimum-japanese", type=int, default=3)
    return parser


def main() -> None:
    """Generate sector, string, and summary reports."""

    parser = build_parser()
    args = parser.parse_args()
    if args.minimum_ascii <= 0 or args.minimum_japanese <= 0:
        parser.error("minimum thresholds must be positive")

    data = args.track.read_bytes()
    sector_count, remainder = divmod(len(data), SECTOR_SIZE)
    if remainder:
        parser.error("track length is not sector-aligned")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    zero_flags: list[bool] = []
    sector_rows = ["sector\toffset\tnonzero\tunique\tentropy\tprefix_hex"]
    for number in range(sector_count):
        start = number * SECTOR_SIZE
        sector = data[start : start + SECTOR_SIZE]
        nonzero = sum(byte != 0 for byte in sector)
        zero_flags.append(nonzero == 0)
        sector_rows.append(
            f"{number}\t0x{start:08X}\t{nonzero}\t{len(set(sector))}\t"
            f"{entropy(sector):.5f}\t{sector[:16].hex(' ')}"
        )
    (args.output_dir / "sector_map.tsv").write_text(
        "\n".join(sector_rows) + "\n",
        encoding="utf-8",
    )

    ascii_rows = ["offset\tsector\twithin_sector\ttext"]
    for offset, text in scan_ascii(data, args.minimum_ascii):
        escaped = text.replace("\\", "\\\\").replace("\t", "\\t")
        ascii_rows.append(
            f"0x{offset:08X}\t{offset // SECTOR_SIZE}\t"
            f"0x{offset % SECTOR_SIZE:03X}\t{escaped}"
        )
    (args.output_dir / "ascii_strings.tsv").write_text(
        "\n".join(ascii_rows) + "\n",
        encoding="utf-8",
    )

    sjis_rows = ["offset\tsector\twithin_sector\tjapanese_chars\ttext"]
    for offset, count, text in scan_shift_jis(data, args.minimum_japanese):
        escaped = text.replace("\\", "\\\\").replace("\t", "\\t")
        sjis_rows.append(
            f"0x{offset:08X}\t{offset // SECTOR_SIZE}\t"
            f"0x{offset % SECTOR_SIZE:03X}\t{count}\t{escaped}"
        )
    (args.output_dir / "shift_jis_strings.tsv").write_text(
        "\n".join(sjis_rows) + "\n",
        encoding="utf-8",
    )

    runs = zero_runs(zero_flags)
    summary = [
        f"bytes={len(data)}",
        f"sectors={sector_count}",
        f"sha256={sha256(args.track)}",
        f"zero_sectors={sum(zero_flags)}",
        f"zero_runs={len(runs)}",
        f"ascii_runs={len(ascii_rows) - 1}",
        f"shift_jis_runs={len(sjis_rows) - 1}",
    ]
    (args.output_dir / "summary.txt").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
