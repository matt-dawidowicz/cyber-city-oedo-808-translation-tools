"""Shared low-overhead file I/O primitives for binary analysis.

Large game payloads should be scanned through a read-only memory map instead of
being copied into Python heap memory repeatedly.  Hash helpers live here so
analysis and build commands do not each implement their own chunk loops.
"""

from __future__ import annotations

import hashlib
import mmap
import os
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_HASH_CHUNK_SIZE = 8 * 1024 * 1024


@contextmanager
def mapped_file(path: pathlib.Path) -> Iterator[mmap.mmap | bytes]:
    """Yield a read-only bytes-like view of *path* without copying the file.

    Empty files cannot be memory-mapped portably, so they are represented by an
    immutable empty ``bytes`` object.  The file descriptor and map are closed
    deterministically when the context exits.
    """

    with path.open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        if size == 0:
            yield b""
            return
        with mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
            yield data


def sha256_file(
    path: pathlib.Path,
    *,
    chunk_size: int = DEFAULT_HASH_CHUNK_SIZE,
) -> str:
    """Return the SHA-256 digest of a file with bounded memory use."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_buffer(data: object) -> str:
    """Return SHA-256 for a contiguous bytes-like object such as an mmap."""

    digest = hashlib.sha256()
    digest.update(data)  # type: ignore[arg-type]
    return digest.hexdigest()
