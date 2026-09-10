#!/usr/bin/env python3
"""Extract plausible natural-language Shift-JIS runs with native filtering."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
from collections.abc import Sequence

from cyber_oedo.analysis.fast_scan import likely_sjis_runs
from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file
from cyber_oedo.text.sjis import (
    ScriptMetrics,
    script_metrics,
    token_pattern as _token_pattern,
)


def token_pattern(minimum_tokens: int):
    """Return the canonical token-run pattern for compatibility callers."""

    return _token_pattern(minimum_tokens)


def metrics(text: str) -> tuple[int, int, int, int, int]:
    """Return legacy tuple metrics while computing them in one pass."""

    result = script_metrics(text)
    return (
        result.hiragana,
        result.katakana,
        result.kanji,
        result.fullwidth,
        result.ascii_printable,
    )


def _plausible(text: str, shape: ScriptMetrics) -> bool:
    """Apply the title-specific natural-language heuristic once."""

    if len(text) < 5:
        return False
    counts = collections.Counter(text)
    if max(counts.values()) / len(text) > 0.55:
        return False
    if shape.ascii_printable > 2 and shape.fullwidth < 4:
        return False
    kana = shape.hiragana + shape.katakana
    natural_sentence = len(text) >= 8 and kana >= 3 and kana / len(text) >= 0.20
    japanese_label = (
        len(text) >= 5 and kana >= 2 and (kana + shape.kanji) / len(text) >= 0.60
    )
    fullwidth_label = shape.fullwidth >= 5 and shape.ascii_printable == 0
    return natural_sentence or japanese_label or fullwidth_label


def plausible(text: str) -> bool:
    """Reject repetitive binary noise while retaining likely text."""

    return _plausible(text, script_metrics(text))


def build_parser() -> argparse.ArgumentParser:
    """Build the broad Shift-JIS discovery command parser."""

    return argparse.ArgumentParser(
        description=(
            "Scan a 2048-byte-sector payload for Shift-JIS runs that "
            "resemble Japanese sentences or labels."
        ),
        epilog=(
            "This is a discovery heuristic. Structured dialogue should "
            "come from extract-dialogue."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Scan a payload map and stream deterministic candidates to TSV."""

    parser = build_parser()
    parser.add_argument(
        "input",
        type=pathlib.Path,
        help="Track 2 payload .bin",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination TSV",
    )
    parser.add_argument(
        "--minimum-tokens",
        type=int,
        default=4,
        metavar="N",
    )
    args = parser.parse_args(argv)
    if args.minimum_tokens <= 0:
        parser.error("--minimum-tokens must be positive")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with (
        mapped_file(args.input) as data,
        args.output.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as output,
    ):
        writer = csv.DictWriter(
            output,
            fieldnames=(
                "offset",
                "sector",
                "within_sector",
                "bytes",
                "characters",
                "hiragana",
                "katakana",
                "kanji",
                "fullwidth",
                "text",
            ),
            delimiter="\t",
        )
        writer.writeheader()
        starts, ends, native_metrics = likely_sjis_runs(
            data,
            args.minimum_tokens,
        )
        for start, end, shape in zip(
            starts,
            ends,
            native_metrics,
            strict=True,
        ):
            offset = int(start)
            raw = data[offset : int(end)]  # type: ignore[index]
            try:
                text = raw.decode("shift_jis")
            except UnicodeDecodeError as error:
                raise AssertionError(
                    "native scanner admitted undecodable Shift-JIS"
                ) from error
            writer.writerow(
                {
                    "offset": f"0x{offset:08X}",
                    "sector": offset // SECTOR_SIZE,
                    "within_sector": (f"0x{offset % SECTOR_SIZE:03X}"),
                    "bytes": len(raw),
                    "characters": int(shape[0]),
                    "hiragana": int(shape[1]),
                    "katakana": int(shape[2]),
                    "kanji": int(shape[3]),
                    "fullwidth": int(shape[4]),
                    "text": text,
                }
            )
            count += 1
    print(f"strings={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
