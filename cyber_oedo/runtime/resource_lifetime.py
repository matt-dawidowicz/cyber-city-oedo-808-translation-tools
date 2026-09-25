"""Map logical address overlap between dialogue and exploration resources.

Logical overlap is not physical CD-RAM ownership proof on the HuC6280 because
MPR mappings may change between overlays. This module intentionally reports
that distinction instead of treating matching CPU addresses as bank identity.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass

from cyber_oedo.runtime.dialogue_residency import (
    MODULE_CPU_END_EXCLUSIVE,
    MODULE_CPU_START,
    SPEAKER_LOCAL_END_EXCLUSIVE,
    SPEAKER_LOCAL_START,
)

SECTOR_BYTES = 0x800


@dataclass(frozen=True, slots=True)
class AddressRange:
    name: str
    start: int
    end_exclusive: int
    domain: str

    @property
    def bytes(self) -> int:
        return self.end_exclusive - self.start


DIALOGUE_MODULE = AddressRange(
    "dialogue_module",
    MODULE_CPU_START,
    MODULE_CPU_END_EXCLUSIVE,
    "cpu_logical",
)
DIALOGUE_SPEAKER = AddressRange(
    "dialogue_speaker_local",
    SPEAKER_LOCAL_START,
    SPEAKER_LOCAL_END_EXCLUSIVE,
    "cpu_logical",
)
EXPLORATION_LOCAL_A = AddressRange(
    "exploration_scene_local_a",
    0x4000,
    0x4000 + 7 * SECTOR_BYTES,
    "cpu_logical",
)
EXPLORATION_LOCAL_B = AddressRange(
    "exploration_scene_local_b",
    0x9000,
    0x9000 + 3 * SECTOR_BYTES,
    "cpu_logical",
)


def overlap(left: AddressRange, right: AddressRange) -> AddressRange | None:
    if left.domain != right.domain:
        return None
    start = max(left.start, right.start)
    end = min(left.end_exclusive, right.end_exclusive)
    if start >= end:
        return None
    return AddressRange(
        f"{left.name}_x_{right.name}",
        start,
        end,
        left.domain,
    )


def _range_json(item: AddressRange) -> dict[str, object]:
    return {
        "name": item.name,
        "start": f"$%04X" % item.start,
        "end_inclusive": f"$%04X" % (item.end_exclusive - 1),
        "bytes": item.bytes,
        "domain": item.domain,
    }


def build_resource_lifetime_report() -> dict[str, object]:
    module_overlap = overlap(DIALOGUE_MODULE, EXPLORATION_LOCAL_B)
    speaker_overlap = overlap(DIALOGUE_SPEAKER, EXPLORATION_LOCAL_B)
    return {
        "ranges": {
            item.name: _range_json(item)
            for item in (
                DIALOGUE_MODULE,
                DIALOGUE_SPEAKER,
                EXPLORATION_LOCAL_A,
                EXPLORATION_LOCAL_B,
            )
        },
        "known_exploration_logical_overlap": {
            "dialogue_module_vs_local_b": (
                None if module_overlap is None else _range_json(module_overlap)
            ),
            "speaker_local_vs_local_b": (
                None if speaker_overlap is None else _range_json(speaker_overlap)
            ),
            "speaker_window_fully_covered": (
                speaker_overlap is not None
                and speaker_overlap.start == DIALOGUE_SPEAKER.start
                and speaker_overlap.end_exclusive == DIALOGUE_SPEAKER.end_exclusive
            ),
        },
        "static_implication": (
            "Known exploration scene-local writes do not overlap the dialogue "
            "module's logical $8000-$8F50 body, but the 3-sector $9000 load "
            "covers the entire logical $9000-$9FFF speaker-local window and "
            "continues through $A7FF."
        ),
        "mpr_caveat": (
            "This is logical-address overlap only. HuC6280 MPR mappings can "
            "change between dialogue and exploration, so it neither proves "
            "speaker clobber nor proves module physical residency. Live MPR or "
            "physical CD-RAM evidence is still required."
        ),
        "optimization_priority": (
            "Keep resident-module and speaker-cache benchmarks independent. "
            "Static overlap makes the speaker-local cache the higher-risk "
            "lifetime assumption; module residency has no equivalent known "
            "logical scene-write overlap."
        ),
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map logical resource overlap across dialogue/exploration."
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_resource_lifetime_report()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
