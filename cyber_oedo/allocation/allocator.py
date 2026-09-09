"""Allocate translated payloads only inside explicitly owned byte regions."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .model import (
    Allocation,
    AllocationPlan,
    AllocationRequest,
    OwnedRegion,
)


class AllocationError(ValueError):
    """Report that a request cannot fit the supplied proven ownership map."""


def _align_up(value: int, alignment: int) -> int:
    """Round *value* upward to the next multiple of *alignment*."""

    return ((value + alignment - 1) // alignment) * alignment


def _validate_regions(regions: tuple[OwnedRegion, ...]) -> None:
    """Reject overlapping ownership claims before placing any data."""

    ordered = sorted(regions, key=lambda item: item.offset)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end_offset > current.offset:
            raise ValueError("owned regions must not overlap")


def allocate_requests(
    regions: Iterable[OwnedRegion],
    requests: Iterable[AllocationRequest],
) -> AllocationPlan:
    """Place requests deterministically with resource-local first fit.

    Regions are considered in ascending payload-offset order. Requests retain
    caller order. No candidate resource region is accepted by this function;
    callers must provide explicit :class:`OwnedRegion` evidence objects.
    """

    owned = tuple(regions)
    pending = tuple(requests)
    _validate_regions(owned)
    keys = [request.key for request in pending]
    if len(set(keys)) != len(keys):
        raise ValueError("allocation request keys must be unique")

    ordered_regions = tuple(sorted(owned, key=lambda item: item.offset))
    cursors = {region: region.offset for region in ordered_regions}
    allocations: list[Allocation] = []

    for request in pending:
        placed: Allocation | None = None
        for region in ordered_regions:
            if region.resource_name != request.resource_name:
                continue
            alignment = math.lcm(region.alignment, request.alignment)
            offset = _align_up(cursors[region], alignment)
            if offset + request.size > region.end_offset:
                continue
            placed = Allocation(
                request=request,
                region=region,
                offset=offset,
            )
            cursors[region] = placed.end_offset
            break
        if placed is None:
            raise AllocationError(
                "no proven owned region can satisfy allocation "
                f"{request.key!r} in resource "
                f"{request.resource_name!r}"
            )
        allocations.append(placed)

    return AllocationPlan(tuple(allocations))


__all__ = ["AllocationError", "allocate_requests"]
