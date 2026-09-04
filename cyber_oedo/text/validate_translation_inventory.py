"""Validate a translator-edited inventory without modifying it."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys

from cyber_oedo.text.build_translation_inventory import OUTPUT_FIELDS


def build_parser() -> argparse.ArgumentParser:
    """Build the inventory-validation command-line parser."""

    parser = argparse.ArgumentParser(
        description="Validate translation-inventory structure and grouping."
    )
    parser.add_argument("inventory", type=pathlib.Path)
    parser.add_argument("--require-translations", action="store_true")
    return parser


def main() -> None:
    """Validate inventory schema, identifiers, ordering, and translations."""

    parser = build_parser()
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    with args.inventory.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        fields = tuple(reader.fieldnames or ())
        missing = [field for field in OUTPUT_FIELDS if field not in fields]
        if missing:
            parser.error("missing required columns: " + ", ".join(missing))
        rows = list(reader)

    entry_ids: set[str] = set()
    previous_offset = -1
    source_by_canonical: dict[str, set[str]] = collections.defaultdict(set)
    canonical_by_source: dict[str, set[str]] = collections.defaultdict(set)
    translations: dict[str, set[str]] = collections.defaultdict(set)

    for row_number, row in enumerate(rows, start=2):
        entry_id = row["entry_id"]
        canonical_id = row["canonical_id"]
        source_text = row["source_text"]
        translation = row["english_translation"].strip()

        if not entry_id or entry_id in entry_ids:
            errors.append(f"row {row_number}: invalid or duplicate entry_id")
        entry_ids.add(entry_id)
        if not canonical_id:
            errors.append(f"row {row_number}: blank canonical_id")

        source_by_canonical[canonical_id].add(source_text)
        canonical_by_source[source_text].add(canonical_id)
        if translation:
            translations[canonical_id].add(translation)
        elif args.require_translations:
            errors.append(f"row {row_number}: blank english_translation")

        try:
            offset = int(row["offset"], 16)
        except ValueError:
            errors.append(f"row {row_number}: invalid offset")
        else:
            if offset < previous_offset:
                errors.append(f"row {row_number}: offsets are out of order")
            previous_offset = offset

        try:
            source_bytes = int(row["source_bytes"])
        except ValueError:
            errors.append(f"row {row_number}: invalid source_bytes")
        else:
            if source_bytes <= 0:
                errors.append(f"row {row_number}: source_bytes must be positive")

    for canonical_id, source_texts in source_by_canonical.items():
        if len(source_texts) > 1:
            errors.append(f"{canonical_id}: multiple source strings")
    for source_text, canonical_ids in canonical_by_source.items():
        if len(canonical_ids) > 1:
            errors.append(f"source {source_text[:40]!r}: split canonical IDs")
    for canonical_id, values in translations.items():
        if len(values) > 1:
            warnings.append(f"{canonical_id}: multiple English translations")

    print(f"rows={len(rows)}")
    print(f"canonical_ids={len(source_by_canonical)}")
    print(
        "translated_rows="
        f"{sum(bool(row['english_translation'].strip()) for row in rows)}"
    )
    print(f"warnings={len(warnings)}")
    print(f"errors={len(errors)}")

    for warning in warnings[:50]:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors[:50]:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
