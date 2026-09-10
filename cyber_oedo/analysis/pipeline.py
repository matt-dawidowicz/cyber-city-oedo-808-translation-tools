"""Run the canonical Tier-A translation analysis as one in-process pipeline."""

from __future__ import annotations

import argparse
import contextlib
import io
import pathlib
import sqlite3
from dataclasses import dataclass
from collections.abc import Sequence

from cyber_oedo.analysis.build_resource_map import write_resource_map
from cyber_oedo.analysis.database import (
    ingest_dialogue,
    ingest_resource_map,
    ingest_translation_inventory,
    initialize_database,
)
from cyber_oedo.analysis.scan_likely_sjis import write_likely_sjis
from cyber_oedo.io import mapped_file, sha256_file
from cyber_oedo.text import (
    build_translation_inventory,
    extract_auxiliary_text,
    validate_translation_inventory,
)
from cyber_oedo.text.extract_dialogue import write_dialogue

ARTIFACT_NAMES = (
    "resource_map.tsv",
    "likely_sjis.tsv",
    "dialogue.tsv",
    "auxiliary.tsv",
    "translation_inventory.tsv",
)
DATABASE_NAME = "analysis.sqlite3"


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Describe generated Tier-A artifacts and their exact identities."""

    output_directory: pathlib.Path
    artifact_hashes: tuple[tuple[str, str], ...]
    row_counts: tuple[tuple[str, int], ...]
    validation_errors: int
    database_path: pathlib.Path | None


def _data_rows(path: pathlib.Path) -> int:
    """Count data rows without interpreting a versioned TSV contract."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return max(0, sum(1 for _ in source) - 1)


def _quiet_main(function: object, argv: list[str]) -> int:
    """Run a retained forensic CLI entry point without duplicating its logic."""

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return int(function(argv))  # type: ignore[operator]


def _build_database(
    output: pathlib.Path,
    resource_map: pathlib.Path,
    dialogue: pathlib.Path,
    inventory: pathlib.Path,
) -> None:
    """Build the generated evidence DB directly from canonical ingest functions."""

    connection = sqlite3.connect(output)
    try:
        initialize_database(connection)
        ingest_resource_map(connection, resource_map)
        ingest_dialogue(connection, dialogue)
        ingest_translation_inventory(connection, inventory)
        connection.commit()
    except BaseException:
        connection.close()
        output.unlink(missing_ok=True)
        raise
    else:
        connection.close()


def run_analysis(
    track: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    minimum_tokens: int = 4,
    build_database: bool = True,
    overwrite: bool = False,
) -> AnalysisResult:
    """Generate the core Tier-A contracts while mapping Track 2 exactly once."""

    if minimum_tokens <= 0:
        raise ValueError("minimum_tokens must be positive")
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    targets = [output_directory / name for name in ARTIFACT_NAMES]
    if build_database:
        targets.append(output_directory / DATABASE_NAME)
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        raise ValueError(
            "analysis output already exists; pass --overwrite to replace: "
            + ", ".join(path.name for path in existing)
        )
    if overwrite:
        for path in existing:
            path.unlink()

    resource_map = output_directory / "resource_map.tsv"
    likely = output_directory / "likely_sjis.tsv"
    dialogue = output_directory / "dialogue.tsv"
    auxiliary = output_directory / "auxiliary.tsv"
    inventory = output_directory / "translation_inventory.tsv"

    # The three payload-dependent stages share one read-only map.  Downstream
    # stages consume their stable TSV contracts and therefore do not remap the
    # 84 MiB payload.
    with mapped_file(track) as data:
        write_resource_map(data, resource_map)
        write_likely_sjis(data, likely, minimum_tokens)
        write_dialogue(data, dialogue)

    if _quiet_main(
        extract_auxiliary_text.main,
        [str(likely), str(dialogue), str(auxiliary)],
    ):
        raise ValueError("auxiliary text extraction failed")
    if _quiet_main(
        build_translation_inventory.main,
        [str(dialogue), str(auxiliary), str(inventory)],
    ):
        raise ValueError("translation inventory build failed")
    validation_status = _quiet_main(
        validate_translation_inventory.main,
        [str(inventory)],
    )
    if validation_status:
        raise ValueError("generated translation inventory failed validation")

    database_path: pathlib.Path | None = None
    if build_database:
        database_path = output_directory / DATABASE_NAME
        _build_database(database_path, resource_map, dialogue, inventory)

    artifact_hashes = tuple((path.name, sha256_file(path)) for path in targets if path.suffix == ".tsv")
    row_counts = tuple((path.name, _data_rows(path)) for path in targets if path.suffix == ".tsv")
    return AnalysisResult(
        output_directory=output_directory,
        artifact_hashes=artifact_hashes,
        row_counts=row_counts,
        validation_errors=0,
        database_path=database_path,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the consolidated Tier-A analysis parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Run the canonical Tier-A translation analysis in process: resource map, "
            "likely Shift-JIS, structured dialogue, auxiliary text, inventory, "
            "validation, and optional SQLite evidence database."
        )
    )
    parser.add_argument("track", type=pathlib.Path, help="Track 2 payload .bin")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--minimum-tokens", type=int, default=4, metavar="N")
    parser.add_argument("--no-database", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run Tier-A analysis and print concise artifact identities."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_analysis(
            args.track,
            args.output_dir,
            minimum_tokens=args.minimum_tokens,
            build_database=not args.no_database,
            overwrite=args.overwrite,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for name, rows in result.row_counts:
        print(f"{name}.rows={rows}")
    for name, digest in result.artifact_hashes:
        print(f"{name}.sha256={digest}")
    if result.database_path is not None:
        print(f"database={result.database_path}")
    print("validation=passed")
    return 0


__all__ = ["AnalysisResult", "ARTIFACT_NAMES", "DATABASE_NAME", "build_parser", "main", "run_analysis"]


if __name__ == "__main__":
    raise SystemExit(main())
