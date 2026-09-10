"""Small canonical helpers for versioned UTF-8-SIG TSV contracts."""

from __future__ import annotations

import csv
import pathlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager


@contextmanager
def tsv_dict_reader(path: pathlib.Path) -> Iterator[csv.DictReader]:
    """Yield a tab-delimited DictReader using the repository's BOM contract."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        yield csv.DictReader(source, delimiter="\t")


@contextmanager
def tsv_dict_writer(
    path: pathlib.Path,
    fieldnames: Sequence[str],
) -> Iterator[csv.DictWriter]:
    """Yield a header-initialized tab-delimited DictWriter."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        yield writer


__all__ = ["tsv_dict_reader", "tsv_dict_writer"]
