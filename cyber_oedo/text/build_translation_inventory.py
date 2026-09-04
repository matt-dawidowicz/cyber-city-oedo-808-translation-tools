"""Build the translator-facing occurrence inventory."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
from collections.abc import Iterator
from typing import Any

from cyber_oedo.contracts import TRANSLATION_INVENTORY_V1

OUTPUT_FIELDS = TRANSLATION_INVENTORY_V1.fields


def read_tsv(path: pathlib.Path) -> Iterator[dict[str, str]]:
    """Yield dictionaries from a UTF-8 tab-separated file."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source, delimiter="\t")


def auxiliary_quality(text: str) -> str:
    """Assign a conservative confidence label to auxiliary text."""

    has_halfwidth = any(
        0xFF61 <= ord(character) <= 0xFF9F
        for character in text
    )
    if has_halfwidth or text.startswith(("`", "'")):
        return "review"
    return "likely_text"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Merge dialogue and auxiliary text TSVs into an editable, "
            "occurrence-level translation inventory."
        )
    )
    parser.add_argument("dialogue", type=pathlib.Path)
    parser.add_argument("auxiliary", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    return parser


def main() -> None:
    """Merge extracted text into a version-1 translation inventory."""

    args = build_parser().parse_args()
    occurrences: list[dict[str, Any]] = []

    for row in read_tsv(args.dialogue):
        occurrences.append(
            {
                "kind": "dialogue",
                "bank": row["bank"],
                "quality": row["quality"],
                "offset": row["offset"],
                "sector": row["sector"],
                "source_bytes": row["record_bytes"],
                "controls": row["controls"],
                "source_text": row["text"],
                "tagged_source": row["tagged_text"],
            }
        )

    for row in read_tsv(args.auxiliary):
        occurrences.append(
            {
                "kind": "auxiliary",
                "bank": row["bank"],
                "quality": auxiliary_quality(row["text"]),
                "offset": row["offset"],
                "sector": row["sector"],
                "source_bytes": row["bytes"],
                "controls": "",
                "source_text": row["text"],
                "tagged_source": row["text"],
            }
        )

    occurrences.sort(key=lambda row: int(str(row["offset"]), 16))
    occurrence_counts = collections.Counter(
        str(row["source_text"]) for row in occurrences
    )
    canonical_ids: dict[str, str] = {}
    output_rows: list[dict[str, Any]] = []

    for index, row in enumerate(occurrences, start=1):
        source_text = str(row["source_text"])
        if source_text not in canonical_ids:
            canonical_ids[source_text] = f"T{len(canonical_ids) + 1:05d}"
        output_rows.append(
            {
                "entry_id": f"E{index:05d}",
                "canonical_id": canonical_ids[source_text],
                "occurrence_count": occurrence_counts[source_text],
                **row,
                "english_translation": "",
                "translator_notes": "",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=OUTPUT_FIELDS,
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    review_count = sum(
        row["quality"] == "review" for row in output_rows
    )
    print(f"occurrences={len(output_rows)}")
    print(f"canonical_texts={len(canonical_ids)}")
    print(f"review_occurrences={review_count}")


if __name__ == "__main__":
    main()
