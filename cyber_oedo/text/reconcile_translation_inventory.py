#!/usr/bin/env python3
"""Reconcile translated inventory fields onto a regenerated structure."""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cyber_oedo.contracts import TRANSLATION_INVENTORY_V1

OUTPUT_FIELDS = TRANSLATION_INVENTORY_V1.fields
REPORT_FIELDS = (
    "entry_id",
    "canonical_id",
    "status",
    "old_entry_id",
    "offset",
    "source_text",
)


@dataclass(frozen=True, slots=True)
class OldTranslation:
    """Store translator fields and occurrence identity for one old row."""

    entry_id: str
    kind: str
    offset: str
    source_text: str
    english_translation: str
    translator_notes: str

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> OldTranslation:
        """Build a normalized old-translation record from one TSV row."""

        return cls(
            entry_id=row["entry_id"],
            kind=row["kind"],
            offset=row["offset"].upper(),
            source_text=row["source_text"],
            english_translation=row["english_translation"],
            translator_notes=row["translator_notes"],
        )


@dataclass(frozen=True, slots=True)
class ReconciliationMatch:
    """Describe one automatic translation-field migration decision."""

    status: str
    source: OldTranslation | None


def _read_rows(path: pathlib.Path) -> list[dict[str, str]]:
    """Read and validate one version-1-compatible inventory TSV."""

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source:
        reader = csv.DictReader(source, delimiter="\t")
        TRANSLATION_INVENTORY_V1.require_compatible_header(reader.fieldnames or ())
        return list(reader)


def _source_consensus(
    old_rows: Sequence[OldTranslation],
) -> dict[str, OldTranslation | None]:
    """Map source text to one unambiguous translated representation."""

    grouped: dict[str, list[OldTranslation]] = collections.defaultdict(list)
    for row in old_rows:
        grouped[row.source_text].append(row)

    consensus: dict[str, OldTranslation | None] = {}
    for source_text, group in grouped.items():
        translated = {
            (row.english_translation, row.translator_notes)
            for row in group
            if row.english_translation
        }
        if len(translated) != 1:
            consensus[source_text] = None
            continue
        english, notes = next(iter(translated))
        exemplar = group[0]
        consensus[source_text] = OldTranslation(
            entry_id=exemplar.entry_id,
            kind=exemplar.kind,
            offset=exemplar.offset,
            source_text=source_text,
            english_translation=english,
            translator_notes=notes,
        )
    return consensus


def _build_matcher(
    old_rows: Sequence[OldTranslation],
) -> tuple[
    dict[tuple[str, str, str], OldTranslation],
    dict[str, OldTranslation | None],
]:
    """Build exact-occurrence and source-consensus lookup tables."""

    exact: dict[tuple[str, str, str], OldTranslation] = {}
    for row in old_rows:
        key = (row.kind, row.offset, row.source_text)
        if key in exact:
            raise ValueError("old inventory contains duplicate physical occurrence key")
        exact[key] = row
    return exact, _source_consensus(old_rows)


def reconcile_row(
    row: Mapping[str, str],
    exact: Mapping[tuple[str, str, str], OldTranslation],
    consensus: Mapping[str, OldTranslation | None],
) -> ReconciliationMatch:
    """Choose the strongest safe automatic match for one regenerated row."""

    key = (
        row["kind"],
        row["offset"].upper(),
        row["source_text"],
    )
    source = exact.get(key)
    if source is not None:
        return ReconciliationMatch("exact_occurrence", source)

    source = consensus.get(row["source_text"])
    if source is not None:
        return ReconciliationMatch("source_consensus", source)
    if row["source_text"] in consensus:
        return ReconciliationMatch("source_conflict", None)
    return ReconciliationMatch("unmatched", None)


def build_parser() -> argparse.ArgumentParser:
    """Build the translation-inventory reconciliation command parser."""

    return argparse.ArgumentParser(
        description=(
            "Copy translator-owned English fields from an older inventory "
            "onto a newly regenerated structural inventory."
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Reconcile old translations while preserving new structural fields."""

    parser = build_parser()
    parser.add_argument("old_inventory", type=pathlib.Path)
    parser.add_argument("new_inventory", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument(
        "--report",
        type=pathlib.Path,
        help="optional per-row reconciliation report TSV",
    )
    args = parser.parse_args(argv)

    old_raw = _read_rows(args.old_inventory)
    new_rows = _read_rows(args.new_inventory)
    old_rows = tuple(OldTranslation.from_row(row) for row in old_raw)
    exact, consensus = _build_matcher(old_rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)

    status_counts: collections.Counter[str] = collections.Counter()
    used_old_entries: set[str] = set()
    report_rows: list[dict[str, str]] = []

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
        for row in new_rows:
            match = reconcile_row(row, exact, consensus)
            status_counts[match.status] += 1
            migrated = dict(row)
            old_entry_id = ""
            if match.source is not None:
                migrated["english_translation"] = match.source.english_translation
                migrated["translator_notes"] = match.source.translator_notes
                old_entry_id = match.source.entry_id
                used_old_entries.add(match.source.entry_id)
            writer.writerow({field: migrated[field] for field in OUTPUT_FIELDS})
            report_rows.append(
                {
                    "entry_id": row["entry_id"],
                    "canonical_id": row["canonical_id"],
                    "status": match.status,
                    "old_entry_id": old_entry_id,
                    "offset": row["offset"],
                    "source_text": row["source_text"],
                }
            )

    if args.report is not None:
        with args.report.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as report:
            writer = csv.DictWriter(
                report,
                fieldnames=REPORT_FIELDS,
                delimiter="\t",
            )
            writer.writeheader()
            writer.writerows(report_rows)

    translated_old = {row.entry_id for row in old_rows if row.english_translation}
    orphaned = translated_old - used_old_entries
    for status in (
        "exact_occurrence",
        "source_consensus",
        "source_conflict",
        "unmatched",
    ):
        print(f"{status}={status_counts[status]}")
    print(f"orphaned_translated_old_entries={len(orphaned)}")
    return 0


__all__ = [
    "OUTPUT_FIELDS",
    "REPORT_FIELDS",
    "OldTranslation",
    "ReconciliationMatch",
    "build_parser",
    "reconcile_row",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
