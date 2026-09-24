"""Map named text-bearing resources back to their loader-directory entries."""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.resources import build_candidate_regions, discover_resource_headers


TRACK2_ABSOLUTE_LBA = 0x0E06
RESOURCE_DIRECTORY_NAME_BYTES = 10
RESOURCE_DIRECTORY_DESCRIPTOR_BYTES = 6


@dataclass(frozen=True, slots=True)
class ResourceLoadSite:
    name: str
    resource_offset: int
    relative_sector: int
    absolute_lba: int
    directory_name_offset: int
    descriptor_offset: int
    descriptor: bytes


def _padded_name(name: str) -> bytes | None:
    encoded = name.encode("ascii", errors="strict")
    if len(encoded) > RESOURCE_DIRECTORY_NAME_BYTES:
        return None
    return encoded.ljust(RESOURCE_DIRECTORY_NAME_BYTES, b"\x00")


def find_resource_load_sites(
    payload: bytes,
    wanted_names: frozenset[str],
) -> tuple[ResourceLoadSite, ...]:
    """Find source-checked name+descriptor directory entries for named resources.

    A directory entry stores a ten-byte zero-padded resource name followed by a
    six-byte descriptor.  The descriptor's first little-endian word is the
    resource's absolute CD LBA.  Matching both name and LBA avoids promoting
    unrelated ASCII occurrences to loader ownership evidence.
    """

    regions = build_candidate_regions(
        discover_resource_headers(payload),
        len(payload) // 2048,
    )
    rows: list[ResourceLoadSite] = []
    for region in regions:
        name = region.header.name
        if name not in wanted_names:
            continue
        name_bytes = _padded_name(name)
        if name_bytes is None:
            continue
        relative_sector = region.start_offset // 2048
        absolute_lba = TRACK2_ABSOLUTE_LBA + relative_sector
        expected_lba = absolute_lba.to_bytes(2, "little")

        start = 0
        while True:
            name_offset = payload.find(name_bytes, start)
            if name_offset < 0:
                break
            descriptor_offset = name_offset + RESOURCE_DIRECTORY_NAME_BYTES
            descriptor = payload[
                descriptor_offset :
                descriptor_offset + RESOURCE_DIRECTORY_DESCRIPTOR_BYTES
            ]
            if len(descriptor) == RESOURCE_DIRECTORY_DESCRIPTOR_BYTES:
                if descriptor[:2] == expected_lba:
                    rows.append(
                        ResourceLoadSite(
                            name=name,
                            resource_offset=region.start_offset,
                            relative_sector=relative_sector,
                            absolute_lba=absolute_lba,
                            directory_name_offset=name_offset,
                            descriptor_offset=descriptor_offset,
                            descriptor=descriptor,
                        )
                    )
            start = name_offset + 1
    return tuple(rows)
