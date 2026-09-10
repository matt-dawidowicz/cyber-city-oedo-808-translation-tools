#!/usr/bin/env python3
"""Extract dialogue records using the canonical Shift-JIS byte model."""

from __future__ import annotations

import argparse
import collections
import pathlib
from collections.abc import Sequence
from dataclasses import dataclass

from cyber_oedo.contracts import DIALOGUE_V1
from cyber_oedo.disc.game_layout import (
    BANKS,
    COMMON_DIALOGUE_CONTROLS,
    DIALOGUE_MARKER,
    SECTOR_SIZE,
    bank_for_offset,
)
from cyber_oedo.io import mapped_file
from cyber_oedo.script import ControlCommand, TextRun, parse_dialogue_body
from cyber_oedo.tabular import tsv_dict_writer

OUTPUT_FIELDS = DIALOGUE_V1.fields


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    """Represent one parsed marker body and its version-1 projection."""

    end_offset: int
    tokens: tuple[str, ...]
    text_only: tuple[str, ...]
    controls: tuple[int, ...]
    sjis_characters: int
    control_opcodes: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DialogueStats:
    """Summary counters for one structured-dialogue extraction."""

    records: int
    unique_tagged_texts: int
    sjis_characters: int
    likely_text: int
    review: int
    bank_counts: tuple[tuple[str, int], ...]


def parse_record(
    data: object,
    start: int,
    limit: int = 1024,
    *,
    allow_unknown_controls: bool = True,
) -> ParsedRecord | None:
    """Parse one dialogue body through the opcode-aware Tier-A parser.

    The returned shape intentionally preserves the historical version-1
    extractor surface. Structured command operands are flattened to raw-byte
    tags in ``tokens`` and ``controls``; callers that need command semantics
    should use :mod:`cyber_oedo.script` directly.

    ``allow_unknown_controls`` defaults to the historical forensic behavior
    for compatibility callers. The normal extraction command disables it so
    generated inventories use only statically established command shapes.
    """

    body = parse_dialogue_body(
        data,
        start,
        limit,
        allow_unknown_controls=allow_unknown_controls,
    )
    if body is None:
        return None

    tokens: list[str] = []
    text_only: list[str] = []
    for node in body.nodes:
        if isinstance(node, TextRun):
            tokens.extend(node.text)
            text_only.extend(node.text)
        elif isinstance(node, ControlCommand):
            tokens.extend(node.legacy_tags())

    return ParsedRecord(
        end_offset=body.end_offset,
        tokens=tuple(tokens),
        text_only=tuple(text_only),
        controls=body.legacy_control_bytes,
        sjis_characters=body.sjis_characters,
        control_opcodes=body.control_opcodes,
    )


def japanese_character_count(text: str) -> int:
    """Count broad Japanese-script characters in visible text."""

    return sum(
        0x3000 <= ord(character) <= 0x30FF or 0x3400 <= ord(character) <= 0x9FFF
        for character in text
    )


def classify_record(
    text: str,
    controls: tuple[int, ...],
) -> str:
    """Classify structured records as likely text or manual review."""

    japanese_count = japanese_character_count(text)
    has_halfwidth = any(0xFF61 <= ord(character) <= 0xFF9F for character in text)
    unexpected = set(controls) - COMMON_DIALOGUE_CONTROLS
    if japanese_count >= 3 and not has_halfwidth and not unexpected:
        return "likely_text"
    return "review"


def build_parser() -> argparse.ArgumentParser:
    """Build the structured-dialogue extraction command parser."""

    return argparse.ArgumentParser(
        description=(
            "Extract opcode-aware Shift-JIS dialogue candidates "
            "introduced by the observed 27 28 record marker."
        )
    )


def write_dialogue(data: object, output_path: pathlib.Path) -> DialogueStats:
    """Write structured dialogue from an already-open payload map."""

    bank_counts: collections.Counter[str] = collections.Counter()
    quality_counts: collections.Counter[str] = collections.Counter()
    unique_tagged_texts: set[str] = set()
    record_count = 0
    total_characters = 0
    with tsv_dict_writer(output_path, OUTPUT_FIELDS) as writer:
        search_at = 0
        while True:
            marker_offset = data.find(DIALOGUE_MARKER, search_at)  # type: ignore[attr-defined]
            if marker_offset < 0:
                break
            parsed = parse_record(
                data,
                marker_offset + len(DIALOGUE_MARKER),
                allow_unknown_controls=False,
            )
            search_at = marker_offset + 1
            if parsed is None:
                continue
            text = "".join(parsed.text_only)
            if parsed.sjis_characters < 2 or japanese_character_count(text) < 2:
                continue
            quality = classify_record(text, parsed.control_opcodes)
            bank = bank_for_offset(marker_offset)
            tagged = "".join(parsed.tokens)
            raw_hex = data[marker_offset : parsed.end_offset + 1].hex(" ")  # type: ignore[index]
            writer.writerow(
                {
                    "bank": bank,
                    "quality": quality,
                    "offset": f"0x{marker_offset:08X}",
                    "sector": marker_offset // SECTOR_SIZE,
                    "within_sector": f"0x{marker_offset % SECTOR_SIZE:03X}",
                    "record_bytes": parsed.end_offset - marker_offset + 1,
                    "sjis_characters": parsed.sjis_characters,
                    "controls": " ".join(f"{value:02X}" for value in parsed.controls),
                    "tagged_text": tagged,
                    "text": text,
                    "raw_hex": raw_hex,
                }
            )
            record_count += 1
            total_characters += parsed.sjis_characters
            bank_counts[bank] += 1
            quality_counts[quality] += 1
            unique_tagged_texts.add(tagged)
    return DialogueStats(
        records=record_count,
        unique_tagged_texts=len(unique_tagged_texts),
        sjis_characters=total_characters,
        likely_text=quality_counts["likely_text"],
        review=quality_counts["review"],
        bank_counts=tuple((bank.name, bank_counts[bank.name]) for bank in BANKS),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Scan a mapped payload and stream structured dialogue rows to TSV."""

    parser = build_parser()
    parser.add_argument("input", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument("output", type=pathlib.Path, help="destination dialogue TSV")
    args = parser.parse_args(argv)
    with mapped_file(args.input) as data:
        stats = write_dialogue(data, args.output)
    print(f"records={stats.records}")
    print(f"unique_tagged_texts={stats.unique_tagged_texts}")
    print(f"sjis_characters={stats.sjis_characters}")
    print(f"likely_text={stats.likely_text}")
    print(f"review={stats.review}")
    for bank, count in stats.bank_counts:
        print(f"{bank}={count}")
    return 0


__all__ = [
    "OUTPUT_FIELDS",
    "ParsedRecord",
    "DialogueStats",
    "parse_record",
    "japanese_character_count",
    "classify_record",
    "build_parser",
    "main",
    "write_dialogue",
]


if __name__ == "__main__":
    raise SystemExit(main())
