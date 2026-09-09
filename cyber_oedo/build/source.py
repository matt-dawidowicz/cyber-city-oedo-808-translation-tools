"""Authenticate the exact CloneCD source set used by build profiles."""

from __future__ import annotations

import pathlib
from collections.abc import Mapping

from cyber_oedo.io import sha256_file


def resolve_source_set(
    source_ccd: pathlib.Path,
    source_hashes: Mapping[str, str],
) -> dict[str, pathlib.Path]:
    """Resolve CCD companions and authenticate every file once."""

    source_ccd = source_ccd.resolve()
    if source_ccd.suffix.lower() != ".ccd":
        raise ValueError("source path must name a .ccd file")
    paths = {
        extension: source_ccd.with_suffix(extension)
        for extension in source_hashes
    }
    for extension, path in paths.items():
        if not path.is_file():
            raise ValueError(
                f"missing CloneCD companion {extension}: {path}"
            )
        actual = sha256_file(path)
        expected = source_hashes[extension]
        if actual != expected:
            raise ValueError(
                f"{path.name}: SHA-256 mismatch; expected {expected}, "
                f"found {actual}"
            )
    return paths
