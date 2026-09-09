"""Verify evidence-gated deterministic allocation behavior."""

from __future__ import annotations

import hashlib
import unittest

from cyber_oedo.allocation import (
    AllocationError,
    AllocationRequest,
    OwnedRegion,
    allocate_requests,
)


def digest(label: str) -> str:
    """Return a stable synthetic SHA-256 digest for test ownership data."""

    return hashlib.sha256(label.encode("ascii")).hexdigest()


class AllocationTests(unittest.TestCase):
    """Keep translation allocation resource-local and deterministic."""

    def test_requests_use_resource_local_first_fit(self) -> None:
        """Place ordered requests into matching regions by payload offset."""

        regions = (
            OwnedRegion(
                "KURUZER",
                0x1000,
                16,
                digest("first"),
                "runtime trace A",
            ),
            OwnedRegion(
                "KURUZER",
                0x2000,
                16,
                digest("second"),
                "runtime trace B",
            ),
            OwnedRegion(
                "MAYA01",
                0x3000,
                16,
                digest("maya"),
                "runtime trace C",
            ),
        )
        requests = (
            AllocationRequest("line-a", "KURUZER", 12),
            AllocationRequest("line-b", "KURUZER", 8),
            AllocationRequest("line-c", "MAYA01", 4),
        )
        plan = allocate_requests(regions, requests)
        self.assertEqual(plan.by_key("line-a").offset, 0x1000)
        self.assertEqual(plan.by_key("line-b").offset, 0x2000)
        self.assertEqual(plan.by_key("line-c").offset, 0x3000)

    def test_alignment_is_respected_without_crossing_resource(self) -> None:
        """Honor combined region/request alignment before placing bytes."""

        region = OwnedRegion(
            "KURUZER",
            0x1000,
            32,
            digest("aligned"),
            "runtime trace",
            alignment=4,
        )
        requests = (
            AllocationRequest("a", "KURUZER", 3, alignment=1),
            AllocationRequest("b", "KURUZER", 4, alignment=8),
        )
        plan = allocate_requests((region,), requests)
        self.assertEqual(plan.by_key("a").offset, 0x1000)
        self.assertEqual(plan.by_key("b").offset, 0x1008)

    def test_missing_resource_capacity_fails_closed(self) -> None:
        """Raise instead of borrowing bytes from a different resource."""

        region = OwnedRegion(
            "MAYA01",
            0x3000,
            64,
            digest("maya"),
            "runtime trace",
        )
        request = AllocationRequest("overflow", "KURUZER", 4)
        with self.assertRaises(AllocationError):
            allocate_requests((region,), (request,))

    def test_insufficient_capacity_fails_closed(self) -> None:
        """Reject a request that exceeds all proven local ownership."""

        region = OwnedRegion(
            "KURUZER",
            0x1000,
            4,
            digest("tiny"),
            "runtime trace",
        )
        request = AllocationRequest("overflow", "KURUZER", 5)
        with self.assertRaises(AllocationError):
            allocate_requests((region,), (request,))

    def test_overlapping_ownership_claims_are_rejected(self) -> None:
        """Refuse ambiguous ownership evidence before allocation begins."""

        regions = (
            OwnedRegion(
                "KURUZER",
                0x1000,
                16,
                digest("a"),
                "trace A",
            ),
            OwnedRegion(
                "OTHER",
                0x1008,
                16,
                digest("b"),
                "trace B",
            ),
        )
        with self.assertRaises(ValueError):
            allocate_requests(regions, ())

    def test_duplicate_request_keys_are_rejected(self) -> None:
        """Require stable unique identities in deterministic plans."""

        region = OwnedRegion(
            "KURUZER",
            0x1000,
            16,
            digest("region"),
            "runtime trace",
        )
        requests = (
            AllocationRequest("same", "KURUZER", 2),
            AllocationRequest("same", "KURUZER", 2),
        )
        with self.assertRaises(ValueError):
            allocate_requests((region,), requests)

    def test_invalid_source_digest_is_rejected(self) -> None:
        """Require exact source identity for every claimed owned region."""

        with self.assertRaises(ValueError):
            OwnedRegion(
                "KURUZER",
                0x1000,
                8,
                "not-a-digest",
                "runtime trace",
            )


if __name__ == "__main__":
    unittest.main()
