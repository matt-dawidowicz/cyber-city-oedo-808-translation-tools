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
    Broad valid Shift-JIS runs. This is reconnaissance, not the canonical
    dialogue extractor; embedded controls split or distort these runs.

Every offset in these files addresses the flat 2048-byte payload, not the raw
2352-byte CloneCD IMG. Run ``extract_track2_mode1.py`` first.

The command reads the complete payload into memory, creates the output
directory, replaces all four report files, and records the input SHA-256 for
reproducibility. The source payload is opened read-only.
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
    """Calculate a file's SHA-256 digest incrementally.

    Args:
        path: File whose exact byte content should be identified.

    Returns:
        A 64-character lowercase hexadecimal digest.

    Raises:
        OSError: If the file cannot be opened or read.

    Notes:
        One-megabyte chunks keep hashing memory use independent of file size.
    """

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entropy(data: bytes) -> float:
    """Calculate Shannon entropy for a byte sequence.

    Args:
        data: Bytes whose value-frequency distribution should be measured.

    Returns:
        Shannon entropy in bits per byte. Empty input returns ``0.0``.

    Notes:
        Entropy is a structural triage metric, not a reliable data-type or
        compression detector.
    """

    if not data:
        return 0.0
    counts = collections.Counter(data)
    length = len(data)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in counts.values()
    )


def zero_runs(flags: list[bool]) -> list[tuple[int, int]]:
    """Convert Boolean sector flags into half-open zero-sector runs.

    Args:
        flags: Sequence in which ``True`` marks an all-zero sector.

    Returns:
        Ordered ``(start, end)`` index pairs for every contiguous true run.
        Single-sector runs are retained.

    Notes:
        A false sentinel is appended to a new list so a run ending at the final
        input element is closed without special-case logic. ``flags`` itself
        is not modified.
    """

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
    """Yield contiguous printable ASCII runs.

    Args:
        data: Binary payload to scan.
        minimum: Minimum number of bytes in a retained run.

    Yields:
        Tuples containing the run's byte offset and decoded ASCII text.

    Raises:
        ValueError: If ``minimum`` is not positive.

    Notes:
        Printable bytes are limited to ``20-7E``. Runs never overlap because
        ``re.finditer`` returns non-overlapping matches.
    """

    if minimum <= 0:
        raise ValueError("minimum must be positive")
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % minimum)
    for match in pattern.finditer(data):
        yield match.start(), match.group().decode("ascii")


def scan_shift_jis(
    data: bytes,
    minimum_japanese: int = 3,
) -> Iterator[tuple[int, int, str]]:
    """Yield broad Shift-JIS-compatible runs with enough Japanese tokens.

    This accepts printable ASCII and whitespace within a run because it is a
    discovery scanner. Values outside those ranges terminate the candidate.

    Args:
        data: Binary payload to scan.
        minimum_japanese: Minimum count of halfwidth or two-byte Shift-JIS
            tokens required to retain a run.

    Yields:
        Tuples of payload offset, Japanese-token count, and decoded text.
        Carriage returns, line feeds, and tabs are escaped for TSV safety.

    Raises:
        ValueError: If ``minimum_japanese`` is not positive.

    Design Decisions:
        Printable ASCII and ``TAB``, ``LF``, and ``CR`` may occur inside a
        discovery run, but do not increase the Japanese-token count. Invalid
        bytes terminate a run. The outer cursor always advances at least one
        byte, preventing an infinite loop while allowing a new candidate to
        begin immediately after a rejected byte.

    Notes:
        This scanner does not understand dialogue markers or control bytes.
        Its output is intentionally broader than the canonical text parser.
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
            decoded = (
                decoded.replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            if decoded:
                yield start, japanese, decoded
        offset = max(offset + 1, start + 1)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser describing structural, ASCII, and broad Shift-JIS inventory
        generation. Input and threshold arguments are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Inventory sector structure, ASCII labels, and broad Shift-JIS "
            "runs in the extracted 2048-byte Track 2 payload."
        )
    )


def main() -> None:
    """Generate sector and string reconnaissance reports.

    Inputs:
        Parses a payload path, output directory, minimum ASCII length, and
        minimum Japanese-token count from command-line arguments.

    Outputs:
        Writes ``sector_map.tsv``, ``ascii_strings.tsv``,
        ``shift_jis_strings.tsv``, and ``summary.txt``. The command does not
        print normal success output.

    Side Effects:
        Creates the output directory, reads the complete payload into memory,
        and replaces all four report files.

    Failure Conditions:
        ``argparse`` exits for non-positive thresholds. A payload whose length
        is not divisible by ``SECTOR_SIZE`` raises ``SystemExit``. File-system
        errors propagate.

    Design Decisions:
        Reports are simple UTF-8 text so every intermediate result can be
        audited without custom tooling. Manual TSV assembly is safe here
        because matched text has tabs and line breaks escaped first.
    """

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
        raise SystemExit(
            "Track length is not sector-aligned: "
            f"remainder {remainder}"
        )

    zero_flags: list[bool] = []
    sector_rows: list[str] = [
        "sector\toffset\tnonzero\tunique\tentropy\tprefix_hex"
    ]
    for sector_number in range(sector_count):
        start = sector_number * SECTOR_SIZE
        sector = data[start : start + SECTOR_SIZE]
        nonzero = sum(byte != 0 for byte in sector)
        zero_flags.append(nonzero == 0)
        sector_rows.append(
            f"{sector_number}\t0x{start:08X}\t{nonzero}\t{len(set(sector))}\t"
            f"{entropy(sector):.5f}\t{sector[:16].hex(' ')}"
        )
    (output_dir / "sector_map.tsv").write_text(
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
    (output_dir / "ascii_strings.tsv").write_text(
        "\n".join(ascii_rows) + "\n",
        encoding="utf-8",
    )

    sjis_rows = ["offset\tsector\twithin_sector\tjapanese_chars\ttext"]
    for offset, japanese, text in scan_shift_jis(data, args.minimum_japanese):
        escaped = text.replace("\\", "\\\\").replace("\t", "\\t")
        sjis_rows.append(
            f"0x{offset:08X}\t{offset // SECTOR_SIZE}\t"
            f"0x{offset % SECTOR_SIZE:03X}\t"
            f"{japanese}\t{escaped}"
        )
    (output_dir / "shift_jis_strings.tsv").write_text(
        "\n".join(sjis_rows) + "\n",
        encoding="utf-8",
    )

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
        f"{start}\t{end}\t{end - start}"
        for start, end in runs
        if end - start >= 2
    )
    (output_dir / "summary.txt").write_text(
        "\n".join(summary) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
