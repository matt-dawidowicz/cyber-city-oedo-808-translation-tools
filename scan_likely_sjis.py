#!/usr/bin/env python3
"""Extract plausible natural-language Shift-JIS runs from a binary payload.

This is the broad text-discovery pass.  It recognizes printable ASCII,
halfwidth Katakana, and valid two-byte Shift-JIS tokens, then applies
language-shape heuristics to reject obvious binary noise.  It does not know
about the game's dialogue marker or control bytes; use ``extract_dialogue.py``
for structured dialogue and ``extract_auxiliary_text.py`` to subtract dialogue
from this result.

False positives and false negatives are expected.  Tune the minimum token count
or the documented ``plausible`` heuristic when exploring another region, and
review every candidate before treating it as patchable text.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re

from game_layout import SECTOR_SIZE


def token_pattern(minimum_tokens: int) -> re.Pattern[bytes]:
    """Compile a byte pattern for contiguous Shift-JIS-compatible tokens."""

    if minimum_tokens <= 0:
        raise ValueError("minimum_tokens must be positive")
    token = (
        rb"(?:"
        rb"[\x20-\x7e]|"
        rb"[\xa1-\xdf]|"
        rb"(?:[\x81-\x9f\xe0-\xef](?:[\x40-\x7e\x80-\xfc]))"
        rb")"
    )
    return re.compile(token + rb"{%d,}" % minimum_tokens)


def metrics(text: str) -> tuple[int, int, int, int, int]:
    """Return counts used by the plausibility filter.

    Order: Hiragana, Katakana, CJK ideographs, fullwidth forms, printable ASCII.
    """

    hiragana = sum(0x3040 <= ord(character) <= 0x309F for character in text)
    katakana = sum(0x30A0 <= ord(character) <= 0x30FF for character in text)
    kanji = sum(0x3400 <= ord(character) <= 0x9FFF for character in text)
    fullwidth = sum(0xFF01 <= ord(character) <= 0xFF60 for character in text)
    ascii_printable = sum(0x20 <= ord(character) <= 0x7E for character in text)
    return hiragana, katakana, kanji, fullwidth, ascii_printable


def plausible(text: str) -> bool:
    """Reject repetitive binary noise while retaining sentences and labels.

    The thresholds are empirical for this disc.  A return value of ``True``
    means "worth reviewing", not "confirmed player-visible text".
    """

    if len(text) < 5:
        return False
    hiragana, katakana, kanji, fullwidth, ascii_printable = metrics(text)
    kana = hiragana + katakana
    counts = collections.Counter(text)
    max_repeat = max(counts.values())
    if max_repeat / len(text) > 0.55:
        return False
    if ascii_printable > 2 and fullwidth < 4:
        return False
    natural_sentence = len(text) >= 8 and kana >= 3 and kana / len(text) >= 0.20
    japanese_label = len(text) >= 5 and kana >= 2 and (kana + kanji) / len(text) >= 0.60
    fullwidth_label = fullwidth >= 5 and ascii_printable == 0
    return natural_sentence or japanese_label or fullwidth_label


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    return argparse.ArgumentParser(
        description=(
            "Scan a 2048-byte-sector payload for Shift-JIS runs that resemble "
            "Japanese sentences or labels."
        ),
        epilog=(
            "This is a discovery heuristic. Structured dialogue should come "
            "from extract_dialogue.py."
        ),
    )


def main() -> None:
    parser = build_parser()
    parser.add_argument("input", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument("output", type=pathlib.Path, help="destination TSV")
    parser.add_argument(
        "--minimum-tokens",
        type=int,
        default=4,
        metavar="N",
        help="minimum contiguous Shift-JIS-compatible tokens (default: 4)",
    )
    args = parser.parse_args()

    data = args.input.read_bytes()
    try:
        pattern = token_pattern(args.minimum_tokens)
    except ValueError as error:
        parser.error(str(error))

    rows: list[dict[str, object]] = []
    for match in pattern.finditer(data):
        try:
            text = match.group().decode("shift_jis")
        except UnicodeDecodeError:
            continue
        if not plausible(text):
            continue
        hiragana, katakana, kanji, fullwidth, _ascii_printable = metrics(text)
        offset = match.start()
        rows.append(
            {
                "offset": f"0x{offset:08X}",
                "sector": offset // SECTOR_SIZE,
                "within_sector": f"0x{offset % SECTOR_SIZE:03X}",
                "bytes": len(match.group()),
                "characters": len(text),
                "hiragana": hiragana,
                "katakana": katakana,
                "kanji": kanji,
                "fullwidth": fullwidth,
                "text": text,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
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
        writer.writerows(rows)
    print(f"strings={len(rows)}")


if __name__ == "__main__":
    main()
