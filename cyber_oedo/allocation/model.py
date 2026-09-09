"""Typed ownership and deterministic allocation models for translated data."""

from __future__ import annotations

from dataclasses import dataclass


def _is_sha256(value: str) -> bool:
    """Return whether *value* is a lowercase or uppercase SHA-256 hex digest."""

    if len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class OwnedRegion:
    """Describe bytes proven writable within one loaded game resource."""

    resource_name: str
    offset: int
    size: int
    source_sha256: str
    evidence: str
    alignment: int = 1

    def __post_init__(self) -> None:
        """Validate ownership metadata and half-open byte geometry."""

        if not self.resource_name:
            raise ValueError("resource_name must not be empty")
        if self.offset < 0:
            raise ValueError("owned-region offset must be non-negative")
        if self.size <= 0:
            raise ValueError("owned-region size must be positive")
        if self.alignment <= 0:
            raise ValueError("owned-region alignment must be positive")
        if self.offset % self.alignment:
            raise ValueError("owned-region offset violates its alignment")
        if not _is_sha256(self.source_sha256):
            raise ValueError("source_sha256 must be a 64-digit hex digest")
        if not self.evidence:
            raise ValueError("ownership evidence must not be empty")

    @property
    def end_offset(self) -> int:
        """Return the exclusive end of the owned byte interval."""

        return self.offset + self.size


@dataclass(frozen=True, slots=True)
class AllocationRequest:
    """Request deterministic storage inside one proven resource."""

    key: str
    resource_name: str
    size: int
    alignment: int = 1

    def __post_init__(self) -> None:
        """Validate request identity, locality, size, and alignment."""

        if not self.key:
            raise ValueError("allocation key must not be empty")
        if not self.resource_name:
            raise ValueError("resource_name must not be empty")
        if self.size <= 0:
            raise ValueError("allocation size must be positive")
        if self.alignment <= 0:
            raise ValueError("allocation alignment must be positive")


@dataclass(frozen=True, slots=True)
class Allocation:
    """Record one request placed within a proven owned region."""

    request: AllocationRequest
    region: OwnedRegion
    offset: int

    def __post_init__(self) -> None:
        """Require locality, alignment, and complete region containment."""

        if self.request.resource_name != self.region.resource_name:
            raise ValueError("allocation crossed its requested resource")
        if self.offset < self.region.offset:
            raise ValueError("allocation begins before its owned region")
        if self.offset % self.request.alignment:
            raise ValueError("allocation violates request alignment")
        if self.end_offset > self.region.end_offset:
            raise ValueError("allocation exceeds its owned region")

    @property
    def end_offset(self) -> int:
        """Return the exclusive allocation end offset."""

        return self.offset + self.request.size


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    """Represent a deterministic non-overlapping allocation result."""

    allocations: tuple[Allocation, ...]

    def __post_init__(self) -> None:
        """Reject duplicate request keys and overlapping allocated ranges."""

        keys = [item.request.key for item in self.allocations]
        if len(set(keys)) != len(keys):
            raise ValueError("allocation request keys must be unique")
        ordered = sorted(self.allocations, key=lambda item: item.offset)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.end_offset > current.offset:
                raise ValueError("allocations must not overlap")

    def by_key(self, key: str) -> Allocation:
        """Return the allocation with *key* or raise ``KeyError``."""

        for allocation in self.allocations:
            if allocation.request.key == key:
                return allocation
        raise KeyError(key)


__all__ = [
    "Allocation",
    "AllocationPlan",
    "AllocationRequest",
    "OwnedRegion",
]
