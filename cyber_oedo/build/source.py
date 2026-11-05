"""Resolve, copy, and authenticate exact CloneCD source sets."""

from __future__ import annotations

import hashlib
import pathlib
import shutil
from collections.abc import Mapping

from cyber_oedo.io import DEFAULT_HASH_CHUNK_SIZE, sha256_file


def resolve_source_paths(
    source_ccd: pathlib.Path,
    source_hashes: Mapping[str, str],
) -> dict[str, pathlib.Path]:
    """Resolve required CloneCD companions without reading file contents."""

    source_ccd = source_ccd.resolve()
    if source_ccd.suffix.lower() != ".ccd":
        raise ValueError("source path must name a .ccd file")
    paths = {
        extension: source_ccd.with_suffix(extension) for extension in source_hashes
    }
    for extension, path in paths.items():
        if not path.is_file():
            raise ValueError(f"missing CloneCD companion {extension}: {path}")
    return paths


def resolve_source_set(
    source_ccd: pathlib.Path,
    source_hashes: Mapping[str, str],
) -> dict[str, pathlib.Path]:
    """Resolve CCD companions and authenticate each source file."""

    paths = resolve_source_paths(source_ccd, source_hashes)
    for extension, path in paths.items():
        actual = sha256_file(path)
        expected = source_hashes[extension]
        if actual != expected:
            raise ValueError(
                f"{path.name}: SHA-256 mismatch; expected {expected}, found {actual}"
            )
    return paths


def _copy_and_hash(
    source: pathlib.Path,
    destination: pathlib.Path,
    *,
    chunk_size: int,
) -> str:
    """Copy one file while hashing the exact source bytes being copied."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with source.open("rb") as input_file, destination.open("wb") as output:
        for chunk in iter(lambda: input_file.read(chunk_size), b""):
            digest.update(chunk)
            output.write(chunk)
    shutil.copystat(source, destination)
    return digest.hexdigest()


def copy_authenticated_source_set(
    source_ccd: pathlib.Path,
    destination_directory: pathlib.Path,
    output_stem: str,
    source_hashes: Mapping[str, str],
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> tuple[dict[str, pathlib.Path], dict[str, pathlib.Path]]:
    """Copy a CloneCD set and authenticate it in the same read pass.

    No copied file is considered usable until every source digest matches.
    Files created here are removed if copying or authentication fails, so an
    unauthenticated partial set cannot be mistaken for build input.
    """

    if not output_stem or output_stem in {".", ".."} or pathlib.Path(output_stem).name != output_stem or "/" in output_stem or chr(92) in output_stem:
        raise ValueError("output_stem must be a single safe filename component")
    source_paths = resolve_source_paths(source_ccd, source_hashes)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destinations = {
        extension: destination_directory / f"{output_stem}{extension}"
        for extension in source_paths
    }
    # Check file identity before any destination is opened for writing.
    for source in source_paths.values():
        for destination in destinations.values():
            if destination.exists() and source.samefile(destination):
                raise ValueError(f"source and destination alias the same file: {destination}")
    existing = [path for path in destinations.values() if path.exists()]
    if existing:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"refusing to overwrite existing output file(s): {names}")
    output_paths: dict[str, pathlib.Path] = {}
    created: list[pathlib.Path] = []
    try:
        for extension, source in source_paths.items():
            destination = destinations[extension]
            created.append(destination)
            actual = _copy_and_hash(
                source,
                destination,
                chunk_size=chunk_size,
            )
            expected = source_hashes[extension]
            if actual != expected:
                raise ValueError(
                    f"{source.name}: SHA-256 mismatch; expected {expected}, "
                    f"found {actual}"
                )
            output_paths[extension] = destination
    except Exception:
        for destination in created:
            destination.unlink(missing_ok=True)
        raise
    return source_paths, output_paths
