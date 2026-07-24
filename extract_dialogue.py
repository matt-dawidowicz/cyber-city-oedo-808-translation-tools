#!/usr/bin/env python3
"""Extract candidate dialogue records from the Track 2 payload.

Observed record shape::

    27 28  <Shift-JIS glyphs and one-byte controls>  00
    ^^^^^                                             ^^
    marker                                            terminator

The scanner deliberately treats every single-byte value below ``80`` as an
opaque control and renders it as ``<$XX>`` in ``tagged_text``.  Normal ASCII
must *not* be inferred from those values: common values such as ``21``, ``2F``,
and ``40`` occur as dialogue bytecode.  Their precise meanings remain unknown.

``likely_text`` and ``review`` are extraction-confidence labels, not statements
about whether a record is visible or safe to patch.  The scanner can find
unreachable, duplicate, or developer-only material.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
from dataclasses import dataclass

from game_layout import (
    BANKS,
    COMMON_DIALOGUE_CONTROLS,
    DIALOGUE_MARKER,
    SECTOR_SIZE,
    bank_for_offset,
)


OUTPUT_FIELDS = (
    "bank",
    "quality",
    "offset",
    "sector",
    "within_sector",
    "record_bytes",
    "sjis_characters",
    "controls",
    "tagged_text",
    "text",
    "raw_hex",
)


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """Decoded contents between the marker and null terminator.

    ``end_offset`` points at the terminating ``00``.  ``tokens`` contains both
    decoded glyphs and control tags, while ``text_only`` omits controls for
    translation deduplication and Japanese-text heuristics.
    """

    end_offset: int
    tokens: tuple[str, ...]
    text_only: tuple[str, ...]
    controls: tuple[int, ...]
    sjis_characters: int


def is_shift_jis_lead(value: int) -> bool:
    """Return whether *value* can begin a two-byte Shift-JIS character."""

    return 0x81 <= value <= 0x9F or 0xE0 <= value <= 0xEF


def is_shift_jis_trail(value: int) -> bool:
    """Return whether *value* can be the second byte of Shift-JIS."""

    return 0x40 <= value <= 0x7E or 0x80 <= value <= 0xFC


def parse_record(data: bytes, start: int, limit: int = 1024) -> ParsedRecord | None:
    """Parse one candidate record beginning immediately after its marker.

    Parsing stops successfully only at a null terminator.  Invalid Shift-JIS,
    an unsupported high byte, end-of-file, or a record longer than ``limit``
    rejects the candidate.  The conservative 1024-byte limit keeps a false
    marker from consuming an arbitrary binary region.
    """

    position = start
    tokens: list[str] = []
    text_only: list[str] = []
    controls: list[int] = []
    sjis_characters = 0
    while position < len(data) and position - start < limit:
        value = data[position]
        if value == 0:
            return ParsedRecord(
                end_offset=position,
                tokens=tuple(tokens),
                text_only=tuple(text_only),
                controls=tuple(controls),
                sjis_characters=sjis_characters,
            )
        if (
            is_shift_jis_lead(value)
            and position + 1 < len(data)
            and is_shift_jis_trail(data[position + 1])
        ):
            raw = data[position : position + 2]
            try:
                character = raw.decode("shift_jis")
            except UnicodeDecodeError:
                return None
            tokens.append(character)
            text_only.append(character)
            sjis_characters += 1
            position += 2
            continue
        if 0xA1 <= value <= 0xDF:
            try:
                character = bytes((value,)).decode("shift_jis")
            except UnicodeDecodeError:
                return None
            tokens.append(character)
            text_only.append(character)
            sjis_characters += 1
            position += 1
            continue
        if value < 0x80:
            controls.append(value)
            tokens.append(f"<${value:02X}>")
            position += 1
            continue
        return None
    return None


def japanese_character_count(text: str) -> int:
    """Count Hiragana, Katakana, CJK punctuation, and common CJK ideographs."""

    return sum(
        0x3000 <= ord(character) <= 0x30FF
        or 0x3400 <= ord(character) <= 0x9FFF
        for character in text
    )


def classify_record(text: str, controls: tuple[int, ...]) -> str:
    """Assign a conservative extraction-confidence label.

    Halfwidth Katakana and uncommon controls are retained but flagged for
    manual review because they have a higher false-positive rate.  This is not
    a translation-quality or reachability judgment.
    """

    japanese_count = japanese_character_count(text)
    has_halfwidth_katakana = any(
        0xFF61 <= ord(character) <= 0xFF9F for character in text
    )
    unexpected_controls = set(controls) - COMMON_DIALOGUE_CONTROLS
    if (
        japanese_count >= 3
        and not has_halfwidth_katakana
        and not unexpected_controls
    ):
        return "likely_text"
    return "review"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    return argparse.ArgumentParser(
        description=(
            "Extract null-terminated Shift-JIS dialogue candidates introduced "
            "by the observed 27 28 record marker."
        ),
        epilog=(
            "Offsets and sectors refer to the extracted 2048-byte Track 2 "
            "payload, not the raw 2352-byte CloneCD IMG."
        ),
    )


def main() -> None:
    parser = build_parser()
    parser.add_argument("input", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument("output", type=pathlib.Path, help="destination dialogue TSV")
    args = parser.parse_args()

    data = args.input.read_bytes()
    rows: list[dict[str, object]] = []
    search_at = 0
    while True:
        marker_offset = data.find(DIALOGUE_MARKER, search_at)
        if marker_offset < 0:
            break
        parsed = parse_record(data, marker_offset + len(DIALOGUE_MARKER))
        # Advance by one byte so adjacent or overlapping candidates are not
        # accidentally skipped during forensic scanning.
        search_at = marker_offset + 1
        if parsed is None:
            continue
        text = "".join(parsed.text_only)
        japanese_count = japanese_character_count(text)
        if parsed.sjis_characters < 2 or japanese_count < 2:
            continue
        quality = classify_record(text, parsed.controls)
        rows.append(
            {
                "bank": bank_for_offset(marker_offset),
                "quality": quality,
                "offset": f"0x{marker_offset:08X}",
                "sector": marker_offset // SECTOR_SIZE,
                "within_sector": f"0x{marker_offset % SECTOR_SIZE:03X}",
                "record_bytes": parsed.end_offset - marker_offset + 1,
                "sjis_characters": parsed.sjis_characters,
                "controls": " ".join(
                    f"{value:02X}" for value in parsed.controls
                ),
                "tagged_text": "".join(parsed.tokens),
                "text": text,
                "raw_hex": data[marker_offset : parsed.end_offset + 1].hex(" "),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=OUTPUT_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    counts = collections.Counter(str(row["bank"]) for row in rows)
    quality_counts = collections.Counter(str(row["quality"]) for row in rows)
    unique_texts = len({str(row["tagged_text"]) for row in rows})
    total_characters = sum(int(row["sjis_characters"]) for row in rows)
    print(f"records={len(rows)}")
    print(f"unique_tagged_texts={unique_texts}")
    print(f"sjis_characters={total_characters}")
    print(f"likely_text={quality_counts['likely_text']}")
    print(f"review={quality_counts['review']}")
    for bank in BANKS:
        print(f"{bank.name}={counts[bank.name]}")


if __name__ == "__main__":
    main()
