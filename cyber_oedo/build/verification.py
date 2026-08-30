"""Validate build plans independently from raw-disc patch application."""

from __future__ import annotations

from cyber_oedo.build import engine
from cyber_oedo.build.plan import PatchPlan


def verify_plan_footprint(plan: PatchPlan) -> None:
    """Require a plan to match the engine's independent sector footprint.

    Args:
        plan: Hash-only patch plan to validate.

    Raises:
        ValueError: If profile identity, title mode, hash shapes, or sector
            footprint differs from the authenticated build engine contract.
    """

    if plan.build_profile != engine.BUILD_PROFILE:
        raise ValueError("patch plan uses an unexpected build profile")
    expected = engine.profile_relative_sectors(plan.title_screen_mode)
    if plan.guarded_relative_sectors != expected:
        raise ValueError("patch plan has an unexpected guarded footprint")
    for entry in plan.entries:
        if entry.byte_count <= 0:
            raise ValueError("patch plan contains an empty replacement")
        for digest in (
            entry.expected_sha256,
            entry.replacement_sha256,
        ):
            if len(digest) != 64:
                raise ValueError("patch plan contains a malformed SHA-256")
            try:
                int(digest, 16)
            except ValueError as error:
                raise ValueError(
                    "patch plan contains a malformed SHA-256"
                ) from error
