"""Summarize a version-1 translation inventory as stable JSON."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
from collections.abc import Sequence

from cyber_oedo.contracts import (
    INVENTORY_SUMMARY_V1,
    TRANSLATION_INVENTORY_V1,
    TranslationInventoryRecord,
)


def summarize(path: pathlib.Path) -> dict[str, object]:
    """Stream a compatible inventory and return versioned summary counts."""

    quality_counts: collections.Counter[str] = collections.Counter()
    canonical_ids: set[str] = set()
    row_count = 0
    translated = 0
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        reader = csv.DictReader(source, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        TRANSLATION_INVENTORY_V1.require_compatible_header(fields)
        for mapping in reader:
            row = TranslationInventoryRecord.from_mapping(mapping)
            row_count += 1
            canonical_ids.add(row.canonical_id)
            quality_counts[row.quality] += 1
            if row.english_translation.strip():
                translated += 1
    return {
        "contract": INVENTORY_SUMMARY_V1.identifier,
        "schema_version": INVENTORY_SUMMARY_V1.version,
        "source_schema": TRANSLATION_INVENTORY_V1.identifier,
        "rows": row_count,
        "canonical_ids": len(canonical_ids),
        "translated_rows": translated,
        "blank_translation_rows": row_count - translated,
        "quality_counts": dict(sorted(quality_counts.items())),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the inventory-summary command-line parser."""

    parser = argparse.ArgumentParser(
        description="Summarize a translator inventory as versioned JSON."
    )
    parser.add_argument("inventory", type=pathlib.Path)
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="optional JSON output path; defaults to standard output",
    )
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write or print the stable JSON inventory summary."""

    args = build_parser().parse_args(argv)
    indent = None if args.compact else 2
    text = (
        json.dumps(
            summarize(args.inventory),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
        )
        + "\n"
    )
    if args.output is None:
        print(text, end="")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
