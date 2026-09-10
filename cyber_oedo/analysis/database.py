"""Build a queryable SQLite view over generated Tier-A analysis artifacts."""

from __future__ import annotations

import csv
import hashlib
import pathlib
import sqlite3
from collections.abc import Mapping

from cyber_oedo.contracts import DIALOGUE_V1, TRANSLATION_INVENTORY_V1

ANALYSIS_DB_SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE resource_candidates (
    resource_sector INTEGER PRIMARY KEY,
    resource_offset INTEGER NOT NULL UNIQUE,
    resource_name TEXT NOT NULL,
    end_sector_exclusive INTEGER NOT NULL,
    end_offset_exclusive INTEGER NOT NULL,
    sector_count INTEGER NOT NULL,
    byte_count INTEGER NOT NULL,
    bank TEXT NOT NULL,
    boundary_source TEXT NOT NULL,
    ownership_status TEXT NOT NULL,
    CHECK (end_sector_exclusive > resource_sector),
    CHECK (end_offset_exclusive > resource_offset),
    CHECK (sector_count > 0),
    CHECK (byte_count > 0)
);

CREATE INDEX resource_candidates_range
ON resource_candidates(resource_offset, end_offset_exclusive);

CREATE INDEX resource_candidates_name
ON resource_candidates(resource_name);

CREATE TABLE dialogue_records (
    offset INTEGER PRIMARY KEY,
    bank TEXT NOT NULL,
    quality TEXT NOT NULL,
    sector INTEGER NOT NULL,
    within_sector INTEGER NOT NULL,
    record_bytes INTEGER NOT NULL,
    sjis_characters INTEGER NOT NULL,
    controls TEXT NOT NULL,
    tagged_text TEXT NOT NULL,
    text TEXT NOT NULL,
    raw_hex TEXT NOT NULL,
    CHECK (offset >= 0),
    CHECK (sector >= 0),
    CHECK (within_sector >= 0),
    CHECK (record_bytes > 0),
    CHECK (sjis_characters >= 0)
);

CREATE INDEX dialogue_records_bank
ON dialogue_records(bank);

CREATE TABLE translation_occurrences (
    entry_id TEXT PRIMARY KEY,
    canonical_id TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL,
    kind TEXT NOT NULL,
    bank TEXT NOT NULL,
    quality TEXT NOT NULL,
    offset INTEGER NOT NULL,
    sector INTEGER NOT NULL,
    source_bytes INTEGER NOT NULL,
    controls TEXT NOT NULL,
    source_text TEXT NOT NULL,
    tagged_source TEXT NOT NULL,
    english_translation TEXT NOT NULL,
    translator_notes TEXT NOT NULL,
    CHECK (offset >= 0),
    CHECK (sector >= 0),
    CHECK (source_bytes > 0)
);

CREATE INDEX translation_occurrences_canonical
ON translation_occurrences(canonical_id);

CREATE INDEX translation_occurrences_offset
ON translation_occurrences(offset);

CREATE INDEX translation_occurrences_bank_kind
ON translation_occurrences(bank, kind);
"""

_RESOURCE_FIELDS = (
    "resource_sector",
    "resource_offset",
    "resource_name",
    "end_sector_exclusive",
    "end_offset_exclusive",
    "sector_count",
    "byte_count",
    "bank",
    "boundary_source",
    "ownership_status",
)


def _parse_int(value: str) -> int:
    """Parse decimal or ``0x``-prefixed integer text."""

    return int(value, 0)


def _sha256_file(path: pathlib.Path) -> str:
    """Return the SHA-256 identity of one generated input artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _reader(path: pathlib.Path) -> tuple[csv.DictReader, object]:
    """Open one UTF-8 TSV and return its reader plus owned file handle."""

    source = path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    )
    return csv.DictReader(source, delimiter="\t"), source


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the version-1 Tier-A analysis schema in an empty database."""

    connection.executescript(_SCHEMA)
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        ("schema_version", str(ANALYSIS_DB_SCHEMA_VERSION)),
    )


def _require_fields(
    fieldnames: list[str] | None,
    required: tuple[str, ...],
) -> None:
    """Require every expected TSV column before ingesting rows."""

    actual = set(fieldnames or ())
    missing = [field for field in required if field not in actual]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))


def ingest_resource_map(
    connection: sqlite3.Connection,
    path: pathlib.Path,
) -> int:
    """Insert all candidate resource-map rows and record their file digest."""

    reader, source = _reader(path)
    try:
        _require_fields(reader.fieldnames, _RESOURCE_FIELDS)
        rows = [
            (
                _parse_int(row["resource_sector"]),
                _parse_int(row["resource_offset"]),
                row["resource_name"],
                _parse_int(row["end_sector_exclusive"]),
                _parse_int(row["end_offset_exclusive"]),
                _parse_int(row["sector_count"]),
                _parse_int(row["byte_count"]),
                row["bank"],
                row["boundary_source"],
                row["ownership_status"],
            )
            for row in reader
        ]
    finally:
        source.close()  # type: ignore[attr-defined]
    connection.executemany(
        """
        INSERT INTO resource_candidates VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("resource_map_sha256", _sha256_file(path)),
    )
    return len(rows)


def ingest_dialogue(
    connection: sqlite3.Connection,
    path: pathlib.Path,
) -> int:
    """Insert version-1 dialogue rows and record their file digest."""

    reader, source = _reader(path)
    try:
        DIALOGUE_V1.require_compatible_header(reader.fieldnames or ())
        rows = [
            (
                _parse_int(row["offset"]),
                row["bank"],
                row["quality"],
                _parse_int(row["sector"]),
                _parse_int(row["within_sector"]),
                _parse_int(row["record_bytes"]),
                _parse_int(row["sjis_characters"]),
                row["controls"],
                row["tagged_text"],
                row["text"],
                row["raw_hex"],
            )
            for row in reader
        ]
    finally:
        source.close()  # type: ignore[attr-defined]
    connection.executemany(
        """
        INSERT INTO dialogue_records VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("dialogue_sha256", _sha256_file(path)),
    )
    return len(rows)


def ingest_translation_inventory(
    connection: sqlite3.Connection,
    path: pathlib.Path,
) -> int:
    """Insert translator inventory rows and record their file digest."""

    reader, source = _reader(path)
    try:
        TRANSLATION_INVENTORY_V1.require_compatible_header(reader.fieldnames or ())
        rows = [
            (
                row["entry_id"],
                row["canonical_id"],
                _parse_int(row["occurrence_count"]),
                row["kind"],
                row["bank"],
                row["quality"],
                _parse_int(row["offset"]),
                _parse_int(row["sector"]),
                _parse_int(row["source_bytes"]),
                row["controls"],
                row["source_text"],
                row["tagged_source"],
                row["english_translation"],
                row["translator_notes"],
            )
            for row in reader
        ]
    finally:
        source.close()  # type: ignore[attr-defined]
    connection.executemany(
        """
        INSERT INTO translation_occurrences VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        rows,
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("translation_inventory_sha256", _sha256_file(path)),
    )
    return len(rows)


def table_counts(connection: sqlite3.Connection) -> Mapping[str, int]:
    """Return row counts for the three primary evidence tables."""

    tables = (
        "resource_candidates",
        "dialogue_records",
        "translation_occurrences",
    )
    return {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in tables
    }


__all__ = [
    "ANALYSIS_DB_SCHEMA_VERSION",
    "ingest_dialogue",
    "ingest_resource_map",
    "ingest_translation_inventory",
    "initialize_database",
    "table_counts",
]
