#!/usr/bin/env python3
"""Build the translator inventory without retaining every occurrence."""

from __future__ import annotations

import argparse
import collections
import csv
import heapq
import pathlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from cyber_oedo.contracts import TRANSLATION_INVENTORY_V1

OUTPUT_FIELDS = TRANSLATION_INVENTORY_V1.fields


@dataclass(frozen=True, slots=True)
class Occurrence:
    """Represent one typed text occurrence before TSV serialization."""

    kind: str
    bank: str
    quality: str
    offset: int
    sector: int
    source_bytes: int
    controls: str
    source_text: str
    tagged_source: str

    def export_base(self) -> dict[str, object]:
        """Return boundary fields in the external inventory representation."""

        return {
            "kind": self.kind,
            "bank": self.bank,
            "quality": self.quality,
            "offset": f"0x{self.offset:08X}",
            "sector": self.sector,
            "source_bytes": self.source_bytes,
            "controls": self.controls,
            "source_text": self.source_text,
            "tagged_source": self.tagged_source,
        }


def read_tsv(path: pathlib.Path) -> Iterator[dict[str, str]]:
    """Yield one dictionary at a time from a UTF-8 TSV file."""

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        yield from csv.DictReader(source, delimiter="\t")


def auxiliary_quality(text: str) -> str:
    """Return the retained quality label for auxiliary text."""

    has_halfwidth = any(0xFF61 <= ord(character) <= 0xFF9F for character in text)
    suspicious_prefix = text.startswith(("`", "'"))
    if has_halfwidth or suspicious_prefix:
        return "review"
    return "likely_text"


def _dialogue_occurrences(
    path: pathlib.Path,
) -> Iterator[Occurrence]:
    """Yield typed dialogue rows while enforcing offset ordering."""

    previous = -1
    for row in read_tsv(path):
        offset = int(row["offset"], 16)
        if offset < previous:
            raise ValueError(f"{path}: rows are not sorted by offset")
        previous = offset
        yield Occurrence(
            "dialogue",
            row["bank"],
            row["quality"],
            offset,
            int(row["sector"]),
            int(row["record_bytes"]),
            row["controls"],
            row["text"],
            row["tagged_text"],
        )


def _auxiliary_occurrences(
    path: pathlib.Path,
) -> Iterator[Occurrence]:
    """Yield typed auxiliary rows while enforcing offset ordering."""

    previous = -1
    for row in read_tsv(path):
        offset = int(row["offset"], 16)
        if offset < previous:
            raise ValueError(f"{path}: rows are not sorted by offset")
        previous = offset
        yield Occurrence(
            "auxiliary",
            row["bank"],
            auxiliary_quality(row["text"]),
            offset,
            int(row["sector"]),
            int(row["bytes"]),
            "",
            row["text"],
            row["text"],
        )


def iter_occurrences(
    dialogue: pathlib.Path,
    auxiliary: pathlib.Path,
) -> Iterator[Occurrence]:
    """Merge already offset-sorted inputs in linear time."""

    yield from heapq.merge(
        _dialogue_occurrences(dialogue),
        _auxiliary_occurrences(auxiliary),
        key=lambda item: item.offset,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the translator-inventory command parser."""

    return argparse.ArgumentParser(
        description=(
            "Merge dialogue and auxiliary text TSVs into an editable, "
            "occurrence-level translation inventory."
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Count canonical text, then stream the merged inventory to disk."""

    parser = build_parser()
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("auxiliary", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args(argv)

    occurrence_counts: collections.Counter[str] = collections.Counter(
        occurrence.source_text
        for occurrence in iter_occurrences(
            args.dialogue,
            args.auxiliary,
        )
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canonical_ids: dict[str, str] = {}
    review_count = 0
    output_count = 0
    with args.output.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as output:
        writer = csv.DictWriter(
            output,
            fieldnames=OUTPUT_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        merged = iter_occurrences(
            args.dialogue,
            args.auxiliary,
        )
        for index, occurrence in enumerate(merged, start=1):
            source_text = occurrence.source_text
            canonical_id = canonical_ids.get(source_text)
            if canonical_id is None:
                canonical_id = f"T{len(canonical_ids) + 1:05d}"
                canonical_ids[source_text] = canonical_id
            writer.writerow(
                {
                    "entry_id": f"E{index:05d}",
                    "canonical_id": canonical_id,
                    "occurrence_count": (occurrence_counts[source_text]),
                    **occurrence.export_base(),
                    "english_translation": "",
                    "translator_notes": "",
                }
            )
            output_count += 1
            if occurrence.quality == "review":
                review_count += 1

    print(f"occurrences={output_count}")
    print(f"canonical_texts={len(canonical_ids)}")
    print(f"review_occurrences={review_count}")
    return 0


__all__ = [
    "OUTPUT_FIELDS",
    "Occurrence",
    "read_tsv",
    "auxiliary_quality",
    "iter_occurrences",
    "build_parser",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
