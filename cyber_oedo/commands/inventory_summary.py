"""Summarize a version-1 translation inventory as stable JSON."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib

from cyber_oedo.contracts import (
    INVENTORY_SUMMARY_V1,
    TRANSLATION_INVENTORY_V1,
    TranslationInventoryRecord,
)


def summarize(path: pathlib.Path) -> dict[str, object]:
    """Read a compatible inventory and return versioned summary counts."""

    rows: list[TranslationInventoryRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        TRANSLATION_INVENTORY_V1.require_compatible_header(fields)
        rows.extend(
            TranslationInventoryRecord.from_mapping(row)
            for row in reader
        )
    quality_counts = collections.Counter(row.quality for row in rows)
    translated = sum(bool(row.english_translation.strip()) for row in rows)
    return {
        "contract": INVENTORY_SUMMARY_V1.identifier,
        "schema_version": INVENTORY_SUMMARY_V1.version,
        "source_schema": TRANSLATION_INVENTORY_V1.identifier,
        "rows": len(rows),
        "canonical_ids": len({row.canonical_id for row in rows}),
        "translated_rows": translated,
        "blank_translation_rows": len(rows) - translated,
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


def main() -> None:
    """Write or print the stable JSON inventory summary."""

    args = build_parser().parse_args()
    indent = None if args.compact else 2
    text = json.dumps(
        summarize(args.inventory),
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
    ) + "\n"
    if args.output is None:
        print(text, end="")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
