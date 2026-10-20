"""Fail-closed P0 executable-code ownership guardrails.

These known-invalid windows are supported by authenticated-source analysis
and natural-watch Mesen traces. The guard deliberately NEVER certifies an
unknown location: absence from this list is not a proof of ownership.

Do not use this module to enable quarantined ADPCM profiles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RejectedRuntimeWindow:
    overlay: str
    start_cpu: int
    end_cpu_exclusive: int
    reason: str


# CPU windows are relevant ONLY when the indicated overlay/module is mapped.
# These spans are grounded by source signatures and/or stock-game write/exec
# traces, not inferred solely from zero bytes in the raw track.
KNOWN_REJECTED_M0B_WINDOWS = (
    RejectedRuntimeWindow(
        overlay="mission0b",
        start_cpu=0x4C93,
        end_cpu_exclusive=0x4CFA,
        reason="old portrait cave overwritten during natural gameplay",
    ),
    RejectedRuntimeWindow(
        overlay="mission0b",
        start_cpu=0x4CFA,
        end_cpu_exclusive=0x4D61,
        reason="reserved by the repaired 103-byte portrait cache",
    ),
    RejectedRuntimeWindow(
        overlay="mission0b",
        start_cpu=0x8F51,
        end_cpu_exclusive=0x8FB0,
        reason=(
            "live dialogue-module tail: original executes and writes to this "
            "window (>=2088 exec / >=190 write callbacks by frame 24000)"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class CaveOwnershipAssessment:
    overlay: str
    start_cpu: int
    end_cpu_exclusive: int
    rejected_regions: tuple[RejectedRuntimeWindow, ...]
    runtime_ownership_certified: bool = False
    multi_mission_certified: bool = False
    release_eligible: bool = False

    @property
    def known_rejected(self) -> bool:
        return bool(self.rejected_regions)


def assess_adpcm_code_cave(
    *, overlay: str, start_cpu: int, code_length: int
) -> CaveOwnershipAssessment:
    """Report known overlap; do not mistake unknown regions for safe ones."""
    if not overlay or not isinstance(overlay, str):
        raise ValueError("overlay must be a nonempty string")
    if not isinstance(start_cpu, int) or not isinstance(code_length, int):
        raise ValueError("start_cpu and code_length must be integers")
    if start_cpu < 0 or code_length <= 0 or start_cpu + code_length > 0x10000:
        raise ValueError("code cave must fit in 16-bit CPU address space")
    end_cpu_exclusive = start_cpu + code_length
    rejected = tuple(
        region
        for region in KNOWN_REJECTED_M0B_WINDOWS
        if region.overlay == overlay
        and start_cpu < region.end_cpu_exclusive
        and region.start_cpu < end_cpu_exclusive
    )
    return CaveOwnershipAssessment(
        overlay=overlay,
        start_cpu=start_cpu,
        end_cpu_exclusive=end_cpu_exclusive,
        rejected_regions=rejected,
    )


def require_release_certified_adpcm_cave(
    *, overlay: str, start_cpu: int, code_length: int
) -> None:
    """Always fail closed until a separately reviewed certification exists.

    Calling this function is not an acknowledgment override. Implementing
    proper runtime evidence and gate review must be a future independent
    engineering change, NOT a caller-supplied 'safe=True' parameter.
    """
    assessment = assess_adpcm_code_cave(
        overlay=overlay, start_cpu=start_cpu, code_length=code_length
    )
    if assessment.known_rejected:
        reasons = "; ".join(region.reason for region in assessment.rejected_regions)
        raise ValueError("known unsafe ADPCM code cave: " + reasons)
    raise ValueError(
        "ADPCM executable region unverified: no overlay ownership, live "
        "residency, transfer, or cross-mission certification"
    )
