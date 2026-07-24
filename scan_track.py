#!/usr/bin/env python3
"""Create a first-pass structural inventory of the extracted Track 2 payload.

Outputs written to ``--output-dir``:

``summary.txt``
    File identity, sector counts, string counts, and long all-zero runs.
``sector_map.tsv``
    Per-sector byte diversity, entropy, and a 16-byte prefix.
``ascii_strings.tsv``
    Contiguous printable ASCII runs, useful for resource names and debug text.
``shift_jis_strings.tsv``
    Broad valid Shift-JIS runs.  This is reconnaissance, not the canonical
    dialogue extractor; embedded controls split or distort these runs.

Every offset in these files addresses the flat 2048-byte payload, not the raw
2352-byte CloneCD IMG.  Run ``extract_track2_mode1.py`` first.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import math
import pathlib
import re
from collections.abc import Iterator

from game_layout import SECTOR_SIZE


def sha256(path: pathlib.Path) -> str:
    """Return a lowercase SHA-256 digest without loading the whole file."""

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
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def zero_runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Convert zero-sector flags into half-open ``(start, end)`` runs."""

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
    """Yield printable ASCII runs and payload byte offsets."""

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    for match in pattern.finditer(data):
        yield match.start(), match.group().decode("ascii")


def scan_shift_jis(
    data: bytes, minimum_japanese: int = 3
) -> Iterator[tuple[int, int, str]]:
    """Yield broad Shift-JIS-compatible runs with at least N Japanese tokens.

    This accepts printable ASCII and whitespace within a run because it is a
    discovery scanner.  Values outside those ranges terminate the candidate.
    """

    if minimum_japanese <= 0:
        raise ValueError("minimum_japanese must be positive")
    offset = 0
    size = len(data)
    while offset < size:
        start = offset
        japanese = 0
        while offset < size:
            first = data[offset]
            if 0x20 <= first <= 0x7E or first in (0x09, 0x0A, 0x0D):
                offset += 1
            elif 0xA1 <= first <= 0xDF:
                japanese += 1
                offset += 1
            elif (
                (0x81 <= first <= 0x9F or 0xE0 <= first <= 0xEF)
                and offset + 1 < size
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
            raw = data[start:offset]
            try:
                decoded = raw.decode("shift_jis")
            except UnicodeDecodeError:
                decoded = ""
            decoded = decoded.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
            if decoded:
                yield start, japanese, decoded
        offset = max(offset + 1, start + 1)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    return argparse.ArgumentParser(
        description=(
            "Inventory sector structure, ASCII labels, and broad Shift-JIS "
            "runs in the extracted 2048-byte Track 2 payload."
        )
    )


def main() -> None:
    parser = build_parser()
    parser.add_argument("track", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        required=True,
        help="directory for summary.txt and TSV inventories",
    )
    parser.add_argument(
        "--minimum-ascii",
        type=int,
        default=4,
        metavar="N",
        help="minimum printable characters in an ASCII run (default: 4)",
    )
    parser.add_argument(
        "--minimum-japanese",
        type=int,
        default=3,
        metavar="N",
        help="minimum Japanese tokens in a broad Shift-JIS run (default: 3)",
    )
    args = parser.parse_args()

    if args.minimum_ascii <= 0:
        parser.error("--minimum-ascii must be positive")
    if args.minimum_japanese <= 0:
        parser.error("--minimum-japanese must be positive")

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    data = args.track.read_bytes()
    sector_count, remainder = divmod(len(data), SECTOR_SIZE)
    if remainder:
        raise SystemExit(f"Track length is not sector-aligned: remainder {remainder}")

    zero_flags: list[bool] = []
    sector_rows: list[str] = ["sector\toffset\tnonzero\tunique\tentropy\tprefix_hex"]
    for sector_number in range(sector_count):
        start = sector_number * SECTOR_SIZE
        sector = data[start : start + SECTOR_SIZE]
        nonzero = sum(byte != 0 for byte in sector)
        zero_flags.append(nonzero == 0)
        sector_rows.append(
            f"{sector_number}\t0x{start:08X}\t{nonzero}\t{len(set(sector))}\t"
            f"{entropy(sector):.5f}\t{sector[:16].hex(' ')}"
        )
    (output_dir / "sector_map.tsv").write_text("\n".join(sector_rows) + "\n", encoding="utf-8")

    ascii_rows = ["offset\tsector\twithin_sector\ttext"]
    for offset, text in scan_ascii(data, args.minimum_ascii):
        escaped = text.replace("\\", "\\\\").replace("\t", "\\t")
        ascii_rows.append(
            f"0x{offset:08X}\t{offset // SECTOR_SIZE}\t0x{offset % SECTOR_SIZE:03X}\t{escaped}"
        )
    (output_dir / "ascii_strings.tsv").write_text("\n".join(ascii_rows) + "\n", encoding="utf-8")

    sjis_rows = ["offset\tsector\twithin_sector\tjapanese_chars\ttext"]
    for offset, japanese, text in scan_shift_jis(data, args.minimum_japanese):
        escaped = text.replace("\\", "\\\\").replace("\t", "\\t")
        sjis_rows.append(
            f"0x{offset:08X}\t{offset // SECTOR_SIZE}\t0x{offset % SECTOR_SIZE:03X}\t"
            f"{japanese}\t{escaped}"
        )
    (output_dir / "shift_jis_strings.tsv").write_text("\n".join(sjis_rows) + "\n", encoding="utf-8")

    runs = zero_runs(zero_flags)
    summary = [
        f"path={args.track.resolve()}",
        f"bytes={len(data)}",
        f"sectors={sector_count}",
        f"sha256={sha256(args.track)}",
        f"zero_sectors={sum(zero_flags)}",
        f"nonzero_sectors={sector_count - sum(zero_flags)}",
        f"zero_runs={len(runs)}",
        f"ascii_runs={len(ascii_rows) - 1}",
        f"shift_jis_runs={len(sjis_rows) - 1}",
        "",
        "long_zero_sector_runs (start inclusive, end exclusive, count):",
    ]
    summary.extend(
        f"{start}\t{end}\t{end - start}" for start, end in runs if end - start >= 2
    )
    (output_dir / "summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
