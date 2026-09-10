#!/usr/bin/env python3
"""Validate an edited translation inventory without materializing it."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
import sys
from collections.abc import Sequence

from cyber_oedo.text.build_translation_inventory import OUTPUT_FIELDS


def build_parser() -> argparse.ArgumentParser:
    """Build the read-only inventory validation command parser."""

    return argparse.ArgumentParser(
        description=(
            "Check a translator-edited inventory for schema damage, "
            "duplicate IDs, invalid offsets, and canonical drift."
        ),
        epilog="The file is read-only; this command never rewrites it.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Validate rows in one streaming pass and report bounded diagnostics."""

    parser = build_parser()
    parser.add_argument(
        "inventory",
        type=pathlib.Path,
        help="translation TSV to check",
    )
    parser.add_argument(
        "--require-translations",
        action="store_true",
        help="treat blank english_translation cells as errors",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    warnings: list[str] = []
    entry_ids: set[str] = set()
    previous_offset = -1
    source_by_canonical: dict[
        str,
        set[str],
    ] = collections.defaultdict(set)
    canonical_by_source: dict[
        str,
        set[str],
    ] = collections.defaultdict(set)
    translations_by_canonical: dict[
        str,
        set[str],
    ] = collections.defaultdict(set)
    row_count = 0
    translated_rows = 0

    with args.inventory.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        reader = csv.DictReader(source, delimiter="\t")
        actual_fields = tuple(reader.fieldnames or ())
        missing_fields = [
            field for field in OUTPUT_FIELDS if field not in actual_fields
        ]
        if missing_fields:
            parser.error("missing required columns: " + ", ".join(missing_fields))

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            entry_id = row["entry_id"]
            canonical_id = row["canonical_id"]
            source_text = row["source_text"]
            translation = row["english_translation"].strip()

            if not entry_id:
                errors.append(f"row {row_number}: blank entry_id")
            elif entry_id in entry_ids:
                errors.append(f"row {row_number}: duplicate entry_id {entry_id!r}")
            entry_ids.add(entry_id)

            if not canonical_id:
                errors.append(f"row {row_number}: blank canonical_id")
            source_by_canonical[canonical_id].add(source_text)
            canonical_by_source[source_text].add(canonical_id)
            if translation:
                translated_rows += 1
                translations_by_canonical[canonical_id].add(translation)
            elif args.require_translations:
                errors.append(f"row {row_number}: blank english_translation")

            try:
                offset = int(row["offset"], 16)
            except ValueError:
                errors.append(
                    f"row {row_number}: invalid hexadecimal offset {row['offset']!r}"
                )
            else:
                if offset < previous_offset:
                    errors.append(
                        f"row {row_number}: offset {row['offset']} is out of order"
                    )
                previous_offset = offset

            try:
                source_bytes = int(row["source_bytes"])
            except ValueError:
                errors.append(
                    f"row {row_number}: invalid source_bytes {row['source_bytes']!r}"
                )
            else:
                if source_bytes <= 0:
                    errors.append(f"row {row_number}: source_bytes must be positive")

    for canonical_id, source_texts in source_by_canonical.items():
        if len(source_texts) > 1:
            errors.append(
                f"{canonical_id}: refers to {len(source_texts)} "
                "different source strings"
            )
    for source_text, canonical_ids in canonical_by_source.items():
        if len(canonical_ids) > 1:
            preview = source_text.replace("\n", "\\n")[:40]
            errors.append(
                f"source {preview!r}: split across canonical IDs "
                f"{', '.join(sorted(canonical_ids))}"
            )
    for canonical_id, translations in translations_by_canonical.items():
        if len(translations) > 1:
            warnings.append(
                f"{canonical_id}: has {len(translations)} "
                "different English translations"
            )

    translated_canonical = sum(
        bool(values) for values in translations_by_canonical.values()
    )
    print(f"rows={row_count}")
    print(f"canonical_ids={len(source_by_canonical)}")
    print(f"translated_rows={translated_rows}")
    print(f"translated_canonical_ids={translated_canonical}")
    print(f"warnings={len(warnings)}")
    print(f"errors={len(errors)}")

    for warning in warnings[:50]:
        print(f"WARNING: {warning}", file=sys.stderr)
    if len(warnings) > 50:
        print(
            f"WARNING: {len(warnings) - 50} additional warnings suppressed",
            file=sys.stderr,
        )
    for error in errors[:50]:
        print(f"ERROR: {error}", file=sys.stderr)
    if len(errors) > 50:
        print(
            f"ERROR: {len(errors) - 50} additional errors suppressed",
            file=sys.stderr,
        )
    if errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
