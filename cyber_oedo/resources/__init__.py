"""Candidate resource discovery and ownership-model primitives."""

from .headers import (
    RESOURCE_NAME,
    build_candidate_regions,
    discover_resource_headers,
    looks_like_resource_name,
    read_sector_header_name,
)
from .model import CandidateResourceRegion, ResourceHeader

__all__ = [
    "RESOURCE_NAME",
    "CandidateResourceRegion",
    "ResourceHeader",
    "build_candidate_regions",
    "discover_resource_headers",
    "looks_like_resource_name",
    "read_sector_header_name",
]
