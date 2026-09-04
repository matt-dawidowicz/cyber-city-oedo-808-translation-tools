"""Extract plausible natural-language Shift-JIS runs from a payload."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import re

from cyber_oedo.disc.game_layout import SECTOR_SIZE


def token_pattern(minimum_tokens: int) -> re.Pattern[bytes]:
    """Compile the broad Shift-JIS-compatible token-run pattern."""

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
    """Count Unicode classes used by the plausibility heuristic."""

    hiragana = sum(0x3040 <= ord(char) <= 0x309F for char in text)
    katakana = sum(0x30A0 <= ord(char) <= 0x30FF for char in text)
    kanji = sum(0x3400 <= ord(char) <= 0x9FFF for char in text)
    fullwidth = sum(0xFF01 <= ord(char) <= 0xFF60 for char in text)
    ascii_printable = sum(0x20 <= ord(char) <= 0x7E for char in text)
    return hiragana, katakana, kanji, fullwidth, ascii_printable


def plausible(text: str) -> bool:
    """Return whether a decoded run is worth manual language review."""

    if len(text) < 5:
        return False
    hiragana, katakana, kanji, fullwidth, ascii_printable = metrics(text)
    kana = hiragana + katakana
    if max(collections.Counter(text).values()) / len(text) > 0.55:
        return False
    if ascii_printable > 2 and fullwidth < 4:
        return False
    natural_sentence = len(text) >= 8 and kana >= 3 and kana / len(text) >= 0.20
    japanese_label = (
        len(text) >= 5
        and kana >= 2
        and (kana + kanji) / len(text) >= 0.60
    )
    fullwidth_label = fullwidth >= 5 and ascii_printable == 0
    return natural_sentence or japanese_label or fullwidth_label


def build_parser() -> argparse.ArgumentParser:
    """Build the broad Shift-JIS scanner argument parser."""

    parser = argparse.ArgumentParser(
        description="Find Shift-JIS runs that resemble Japanese text."
    )
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--minimum-tokens", type=int, default=4, metavar="N")
    return parser


def main() -> None:
    """Scan the payload and write likely natural-language candidates."""

    parser = build_parser()
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
        hiragana, katakana, kanji, fullwidth, _ = metrics(text)
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
    fieldnames = (
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
    )
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print(f"strings={len(rows)}")


if __name__ == "__main__":
    main()
