"""Deterministic layout planning for expandable Track-2 resources.

This module does not assume original resource extents are sacred. It plans
new sector-aligned placement for resources whose loader contracts are proven
and emits descriptor-field replacements separately from raw resource bytes.

The first supported descriptor shape is the common 16-byte named-resource
table: name[10], u16 sector, u8 sector_span, u24 byte_length.

``relink_named_resource`` turns one rebuilt resource into source-guarded
payload patches: the bytes go into authenticated all-zero sectors inside the
linker's own window at the end of Track 2, and only the descriptor's LBA,
span and length change.  The original sectors are left untouched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.disc.game_layout import TRACK2_START_LBA
from cyber_oedo.disc.named_resources import (
    RESOURCE_HEADER_BYTES,
    NamedResourceDescriptor,
    descriptor_references,
    max_resource_length,
)

SECTOR_BYTES = 2048

# Track 2 relative sectors 41049-41198 are authenticated zero fill.  Other
# experiments already claim 41049-41068 (English pool and VWF cells) and 41190
# (PR #53 ADPCM sidecar), so relinked resources own this window only.
LINK_WINDOW_START_RELATIVE = 41120
LINK_WINDOW_END_RELATIVE = 41190


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


@dataclass(frozen=True, slots=True)
class NamedResourceRelink:
    """Guarded patches that move one named resource to new sectors."""

    descriptor: NamedResourceDescriptor
    linked: LinkedResource
    descriptor_tail: bytes
    patches: tuple[PayloadPatch, ...]

    @property
    def relative_sector(self) -> int:
        return self.linked.start_sector - TRACK2_START_LBA


@dataclass(frozen=True, slots=True)
class RelinkRequest:
    """One rebuilt resource and the heap address it will load at."""

    descriptor: NamedResourceDescriptor
    data: bytes
    load_address: int


def relink_named_resources(
    payload: bytes | memoryview,
    requests: Sequence[RelinkRequest],
    *,
    window_start_relative: int = LINK_WINDOW_START_RELATIVE,
    window_end_relative: int = LINK_WINDOW_END_RELATIVE,
) -> tuple[NamedResourceRelink, ...]:
    """Place rebuilt resources back to back in owned zero sectors.

    Each request's ``load_address`` is where that resource loads on the
    route being certified; its rebuilt length must stay below the loader's
    ``$D800`` bound from there.  The 16-byte resource header must be
    unchanged because it is part of the loaded image even though the loader
    strips it.  Only each descriptor's LBA, span and length change.
    """

    if not requests:
        raise ResourceLinkError("at least one resource is required")
    if not window_start_relative < window_end_relative:
        raise ResourceLinkError("link window is empty")
    if window_start_relative < LINK_WINDOW_START_RELATIVE or window_end_relative > LINK_WINDOW_END_RELATIVE:
        raise ResourceLinkError("link window extends outside the owned linker window")
    for request in requests:
        descriptor, data = request.descriptor, request.data
        source_start = descriptor.resource_payload_offset
        header = bytes(payload[source_start : source_start + RESOURCE_HEADER_BYTES])
        if data[:RESOURCE_HEADER_BYTES] != header:
            raise ResourceLinkError(f"{descriptor.name}: rebuilt resource changes its 16-byte header")
        limit = max_resource_length(request.load_address)
        if len(data) > limit:
            raise ResourceLinkError(
                f"{descriptor.name}: {len(data)} bytes exceeds the {limit}-byte heap bound "
                f"at ${request.load_address:04X}"
            )

    linked_rows = link_resources(
        (
            ResourceObject(
                request.descriptor.name,
                request.data,
                original_sector=request.descriptor.absolute_lba,
                original_span=request.descriptor.span,
            )
            for request in requests
        ),
        start_sector=TRACK2_START_LBA + window_start_relative,
    )
    if linked_rows[-1].end_sector > TRACK2_START_LBA + window_end_relative:
        raise ResourceLinkError("rebuilt resources overflow the link window")

    results = []
    for request, linked in zip(requests, linked_rows, strict=True):
        descriptor = request.descriptor
        target = range(linked.start_sector, linked.end_sector)
        blob_start = (linked.start_sector - TRACK2_START_LBA) * SECTOR_BYTES
        blob_size = linked.sector_span * SECTOR_BYTES
        if any(payload[blob_start : blob_start + blob_size]):
            raise ResourceLinkError(f"{descriptor.name}: target sectors are not authenticated zero fill")
        references = descriptor_references(payload, target)
        if references:
            raise ResourceLinkError(f"{descriptor.name}: target sectors are already named by {references}")

        tail = bytes((linked.start_sector >> 16,)) + descriptor_fields(linked)
        blob = build_resource_blob((linked,), start_sector=linked.start_sector)
        patches = (
            PayloadPatch(
                blob_start,
                bytes(blob_size),
                blob,
                f"{descriptor.name} relinked to LBA 0x{linked.start_sector:04X}",
            ),
            PayloadPatch(
                descriptor.mutable_tail_offset,
                descriptor.raw[9:],
                tail,
                f"{descriptor.name} descriptor LBA/span/length",
            ),
        )
        results.append(NamedResourceRelink(descriptor, linked, tail, patches))
    return tuple(results)


def relink_named_resource(
    payload: bytes | memoryview,
    descriptor: NamedResourceDescriptor,
    data: bytes,
    *,
    load_address: int,
    window_start_relative: int = LINK_WINDOW_START_RELATIVE,
    window_end_relative: int = LINK_WINDOW_END_RELATIVE,
) -> NamedResourceRelink:
    """Place one rebuilt resource in owned zero sectors and repoint it."""

    return relink_named_resources(
        payload,
        (RelinkRequest(descriptor, data, load_address),),
        window_start_relative=window_start_relative,
        window_end_relative=window_end_relative,
    )[0]
