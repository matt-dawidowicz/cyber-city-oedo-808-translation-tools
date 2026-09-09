"""Evidence-gated allocation primitives for translated resource data."""

from .allocator import AllocationError, allocate_requests
from .model import (
    Allocation,
    AllocationPlan,
    AllocationRequest,
    OwnedRegion,
)

__all__ = [
    "Allocation",
    "AllocationError",
    "AllocationPlan",
    "AllocationRequest",
    "OwnedRegion",
    "allocate_requests",
]
