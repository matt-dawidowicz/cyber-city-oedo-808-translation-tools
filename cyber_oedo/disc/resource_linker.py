"""Deterministic layout planning for expandable Track-2 resources.

This module does not assume original resource extents are sacred. It plans
new sector-aligned placement for resources whose loader contracts are proven
and emits descriptor-field replacements separately from raw resource bytes.

The first supported descriptor shape is the common 16-byte named-resource
table: name[10], u16 sector, u8 sector_span, u24 byte_length.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

SECTOR_BYTES = 2048


class ResourceLinkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResourceObject:
    """One linkable CD resource with compiled bytes and alignment policy."""

    name: str
    data: bytes
    alignment_sectors: int = 1
    original_sector: int | None = None
    original_span: int | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ResourceLinkError("resource name must not be empty")
        if not self.data:
            raise ResourceLinkError(f"{self.name}: resource data must not be empty")
        if self.alignment_sectors <= 0:
            raise ResourceLinkError(f"{self.name}: alignment must be positive")

    @property
    def byte_length(self) -> int:
        return len(self.data)

    @property
    def sector_span(self) -> int:
        return math.ceil(len(self.data) / SECTOR_BYTES)


@dataclass(frozen=True, slots=True)
class LinkedResource:
    name: str
    start_sector: int
    sector_span: int
    byte_length: int
    data: bytes
    original_sector: int | None = None
    original_span: int | None = None

    @property
    def end_sector(self) -> int:
        return self.start_sector + self.sector_span

    @property
    def moved(self) -> bool:
        return self.original_sector is not None and self.start_sector != self.original_sector

    @property
    def grew(self) -> bool:
        return self.original_span is not None and self.sector_span > self.original_span


def _align_sector(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def link_resources(
    resources: Iterable[ResourceObject],
    *,
    start_sector: int,
) -> tuple[LinkedResource, ...]:
    """Place resources sequentially with deterministic sector alignment."""
    if start_sector < 0:
        raise ResourceLinkError("start_sector must be non-negative")
    cursor = start_sector
    linked: list[LinkedResource] = []
    names: set[str] = set()
    for resource in resources:
        if resource.name in names:
            raise ResourceLinkError(f"duplicate resource name: {resource.name}")
        names.add(resource.name)
        cursor = _align_sector(cursor, resource.alignment_sectors)
        row = LinkedResource(
            name=resource.name,
            start_sector=cursor,
            sector_span=resource.sector_span,
            byte_length=resource.byte_length,
            data=resource.data,
            original_sector=resource.original_sector,
            original_span=resource.original_span,
        )
        linked.append(row)
        cursor = row.end_sector
    return tuple(linked)


def descriptor_fields(resource: LinkedResource) -> bytes:
    """Encode the mutable six-byte tail of a common resource descriptor."""
    if resource.start_sector > 0xFFFF:
        raise ResourceLinkError(f"{resource.name}: sector exceeds u16 descriptor")
    if resource.sector_span > 0xFF:
        raise ResourceLinkError(f"{resource.name}: span exceeds u8 descriptor")
    if resource.byte_length > 0xFFFFFF:
        raise ResourceLinkError(f"{resource.name}: length exceeds u24 descriptor")
    return (
        resource.start_sector.to_bytes(2, "little")
        + bytes((resource.sector_span,))
        + resource.byte_length.to_bytes(3, "little")
    )


def build_resource_blob(
    linked: Iterable[LinkedResource],
    *,
    start_sector: int,
) -> bytes:
    """Build the packed sector image for an already-linked resource sequence."""
    rows = tuple(linked)
    if not rows:
        return b""
    end_sector = max(row.end_sector for row in rows)
    if any(row.start_sector < start_sector for row in rows):
        raise ResourceLinkError("linked resource precedes blob start")
    blob = bytearray((end_sector - start_sector) * SECTOR_BYTES)
    occupied: list[tuple[int, int, str]] = []
    for row in rows:
        start = (row.start_sector - start_sector) * SECTOR_BYTES
        end = start + row.byte_length
        for old_start, old_end, old_name in occupied:
            if start < old_end and end > old_start:
                raise ResourceLinkError(f"{row.name} overlaps {old_name}")
        occupied.append((start, (row.end_sector - start_sector) * SECTOR_BYTES, row.name))
        blob[start:end] = row.data
    return bytes(blob)
