#!/usr/bin/env python3
"""Build a local SQLite evidence database from generated Tier-A artifacts."""

from __future__ import annotations

import argparse
import pathlib
import sqlite3
from collections.abc import Sequence

from .database import (
    ingest_dialogue,
    ingest_resource_map,
    ingest_translation_inventory,
    initialize_database,
    table_counts,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the generated analysis-database command parser."""

    return argparse.ArgumentParser(
        description=(
            "Build a queryable local SQLite database from generated "
            "resource, dialogue, and translation TSV artifacts."
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Create one evidence database and ingest selected source artifacts."""

    parser = build_parser()
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination SQLite database",
    )
    parser.add_argument(
        "--resource-map",
        type=pathlib.Path,
        help="candidate resource-map TSV",
    )
    parser.add_argument(
        "--dialogue",
        type=pathlib.Path,
        help="dialogue TSV",
    )
    parser.add_argument(
        "--inventory",
        type=pathlib.Path,
        help="translation inventory TSV",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing generated database",
    )
    args = parser.parse_args(argv)

    selected = (
        args.resource_map,
        args.dialogue,
        args.inventory,
    )
    if not any(selected):
        parser.error(
            "at least one of --resource-map, --dialogue, or --inventory "
            "is required"
        )
    if args.output.exists():
        if not args.overwrite:
            parser.error(
                "output already exists; pass --overwrite to replace it"
            )
        args.output.unlink()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(args.output)
    try:
        initialize_database(connection)
        if args.resource_map is not None:
            ingest_resource_map(connection, args.resource_map)
        if args.dialogue is not None:
            ingest_dialogue(connection, args.dialogue)
        if args.inventory is not None:
            ingest_translation_inventory(connection, args.inventory)
        connection.commit()
        counts = table_counts(connection)
    except BaseException:
        connection.close()
        args.output.unlink(missing_ok=True)
        raise
    else:
        connection.close()

    for table, count in counts.items():
        print(f"{table}={count}")
    return 0


__all__ = ["build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
