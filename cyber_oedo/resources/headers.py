"""Discover sector-aligned candidate resource headers in Track 2 payloads."""

from __future__ import annotations

import re
from collections.abc import Iterable

from cyber_oedo.disc.game_layout import SECTOR_SIZE

from .model import CandidateResourceRegion, ResourceHeader

RESOURCE_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,15}$")
_RESOURCE_NAME_BYTES = frozenset(
    range(ord("A"), ord("Z") + 1)
) | frozenset(range(ord("0"), ord("9") + 1)) | frozenset({ord("_")})


def looks_like_resource_name(text: str) -> bool:
    """Return whether *text* resembles an observed resource identifier."""

    if RESOURCE_NAME.fullmatch(text) is None:
        return False
    return len(text) < 4 or len(set(text)) > 1


def read_sector_header_name(
    data: object,
    sector: int,
    *,
    sector_size: int = SECTOR_SIZE,
) -> str | None:
    """Read one plausible identifier beginning exactly at a sector boundary."""

    if sector < 0:
        raise ValueError("sector must be non-negative")
    if sector_size <= 0:
        raise ValueError("sector_size must be positive")
    start = sector * sector_size
    size = len(data)  # type: ignore[arg-type]
    if start >= size:
        return None
    first = data[start]  # type: ignore[index]
    if not ord("A") <= first <= ord("Z"):
        return None

    end = start
    maximum_end = min(start + 16, size)
    while (
        end < maximum_end
        and data[end] in _RESOURCE_NAME_BYTES  # type: ignore[index]
    ):
        end += 1
    if end == maximum_end and end < size:
        if data[end] in _RESOURCE_NAME_BYTES:  # type: ignore[index]
            return None
    try:
        text = bytes(data[start:end]).decode("ascii")  # type: ignore[index]
    except UnicodeDecodeError:
        return None
    return text if looks_like_resource_name(text) else None


def discover_resource_headers(
    data: object,
    *,
    sector_size: int = SECTOR_SIZE,
) -> tuple[ResourceHeader, ...]:
    """Scan every complete sector for plausible boundary-aligned headers."""

    if sector_size <= 0:
        raise ValueError("sector_size must be positive")
    sector_count, remainder = divmod(
        len(data),  # type: ignore[arg-type]
        sector_size,
    )
    if remainder:
        raise ValueError("payload length must be sector-aligned")
    headers: list[ResourceHeader] = []
    for sector in range(sector_count):
        name = read_sector_header_name(
            data,
            sector,
            sector_size=sector_size,
        )
        if name is not None:
            headers.append(ResourceHeader(sector=sector, name=name))
    return tuple(headers)


def build_candidate_regions(
    headers: Iterable[ResourceHeader],
    total_sectors: int,
) -> tuple[CandidateResourceRegion, ...]:
    """Bound each candidate header by the next header or payload end."""

    if total_sectors <= 0:
        raise ValueError("total_sectors must be positive")
    ordered = tuple(sorted(headers))
    seen: set[int] = set()
    for header in ordered:
        if header.sector >= total_sectors:
            raise ValueError("resource header lies outside the payload")
        if header.sector in seen:
            raise ValueError("resource headers must have unique sectors")
        seen.add(header.sector)

    regions: list[CandidateResourceRegion] = []
    for index, header in enumerate(ordered):
        if index + 1 < len(ordered):
            end_sector = ordered[index + 1].sector
            boundary_source = "next_candidate_header"
        else:
            end_sector = total_sectors
            boundary_source = "track_end"
        regions.append(
            CandidateResourceRegion(
                header=header,
                end_sector=end_sector,
                boundary_source=boundary_source,
            )
        )
    return tuple(regions)


__all__ = [
    "RESOURCE_NAME",
    "build_candidate_regions",
    "discover_resource_headers",
    "looks_like_resource_name",
    "read_sector_header_name",
]
