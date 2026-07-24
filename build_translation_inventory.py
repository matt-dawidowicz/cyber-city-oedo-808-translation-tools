#!/usr/bin/env python3
"""Merge extracted text into the translator-facing occurrence inventory.

The output deliberately keeps one row per binary occurrence. ``entry_id`` is
therefore unique for each location, while ``canonical_id`` groups rows with the
same visible ``source_text`` so a translator can reuse wording. Canonical IDs
do *not* imply byte-identical records: two occurrences can share visible text
but have different control tags or byte lengths.

Only ``english_translation`` and ``translator_notes`` are intended for routine
manual editing. Offsets, source bytes, controls, IDs, and source text form the
analysis key and should be regenerated rather than hand-edited.

Inputs are the dialogue and auxiliary TSVs produced by the extraction pipeline.
Output is a UTF-8-with-BOM TSV suitable for spreadsheet editing. The command
creates the destination directory, replaces the requested inventory, and
prints summary counts; it does not modify either source TSV.
"""

from __future__ import annotations

import argparse
import collections
import csv
import pathlib
from collections.abc import Iterator
from typing import Any


OUTPUT_FIELDS = (
    "entry_id",
    "canonical_id",
    "occurrence_count",
    "kind",
    "bank",
    "quality",
    "offset",
    "sector",
    "source_bytes",
    "controls",
    "source_text",
    "tagged_source",
    "english_translation",
    "translator_notes",
)


def read_tsv(path: pathlib.Path) -> Iterator[dict[str, str]]:
    """Yield dictionaries from a UTF-8 tab-separated file.

    Args:
        path: TSV file to read. An optional UTF-8 byte-order mark is accepted.

    Yields:
        One dictionary per data row, keyed by the file's header names.

    Raises:
        OSError: If the file cannot be opened or read.
        csv.Error: If the CSV parser encounters malformed quoted data.

    Side Effects:
        Opens the source file when iteration begins and closes it when the
        generator is exhausted or closed.
    """

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source, delimiter="\t")


def auxiliary_quality(text: str) -> str:
    """Assign an extraction-confidence label to auxiliary text.

    Args:
        text: Decoded auxiliary candidate from ``scan_likely_sjis.py``.

    Returns:
        ``"review"`` for text containing halfwidth Katakana or beginning with
        a backtick or apostrophe; otherwise ``"likely_text"``.

    Design Decisions:
        The heuristic retains suspicious text instead of discarding it.
        Punctuation-prefixed and halfwidth candidates produced more binary
        false positives during this title-specific analysis.
    """

    has_halfwidth = any(
        0xFF61 <= ord(character) <= 0xFF9F
        for character in text
    )
    if has_halfwidth or text.startswith(("`", "'")):
        return "review"
    return "likely_text"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        A parser explaining the occurrence-level inventory and editable
        columns. Positional paths are added by ``main``.
    """

    return argparse.ArgumentParser(
        description=(
            "Merge dialogue and auxiliary text TSVs into an editable, "
            "occurrence-level translation inventory."
        ),
        epilog=(
            "Translate in english_translation and annotate uncertain context "
            "in translator_notes. Preserve all other columns."
        ),
    )


def main() -> None:
    """Merge extracted text and write the translator-facing inventory.

    Inputs:
        Parses dialogue, auxiliary, and destination TSV paths from command-line
        arguments.

    Outputs:
        Writes rows ordered by payload offset using ``OUTPUT_FIELDS``. Prints
        occurrence, canonical-text, and manual-review counts.

    Side Effects:
        Reads both input TSVs, creates the output parent directory, and
        replaces the destination inventory.

    Failure Conditions:
        File-system and CSV errors propagate. Missing required columns raise
        ``KeyError``. Malformed hexadecimal offsets raise ``ValueError``.

    Design Decisions:
        ``entry_id`` identifies an occurrence, while ``canonical_id`` groups
        identical visible source text. Grouping deliberately ignores control
        tags so translators can compare repeated wording, but each occurrence
        retains its own control evidence and byte length.
    """

    parser = build_parser()
    parser.add_argument(
        "dialogue",
        type=pathlib.Path,
        help="TSV produced by extract_dialogue.py",
    )
    parser.add_argument(
        "auxiliary",
        type=pathlib.Path,
        help="TSV produced by extract_auxiliary_text.py",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination translator-facing TSV",
    )
    args = parser.parse_args()

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
        str(row["source_text"])
        for row in occurrences
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
    print(f"occurrences={len(output_rows)}")
    print(f"canonical_texts={len(canonical_ids)}")
    print(
        "review_occurrences="
        f"{sum(row['quality'] == 'review' for row in output_rows)}"
    )


if __name__ == "__main__":
    main()
