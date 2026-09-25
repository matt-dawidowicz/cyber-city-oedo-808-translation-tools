"""Analyze static seek geometry for the known hot exploration scene bundles."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from dataclasses import dataclass

from cyber_oedo.runtime.cd_load_optimization import HOT_ASSETS, SECTOR_BYTES


@dataclass(frozen=True, slots=True)
class SceneTransfer:
    name: str
    lba: int
    sectors_touched: int

    @property
    def end_lba_exclusive(self) -> int:
        return self.lba + self.sectors_touched


def _asset(name: str) -> SceneTransfer:
    item = next(asset for asset in HOT_ASSETS if asset.name == name)
    return SceneTransfer(
        name=item.name,
        lba=item.sector,
        sectors_touched=math.ceil(item.byte_length / SECTOR_BYTES),
    )


MAIN_SCENE = (
    _asset("main_scene_local_a"),
    _asset("main_scene_local_b"),
    _asset("main_scene_vram"),
)
ALTERNATE_SCENE = (
    _asset("alternate_scene_local"),
    _asset("alternate_scene_vram"),
)


def analyze_sequence(rows: tuple[SceneTransfer, ...]) -> dict[str, object]:
    transitions = []
    total_gap = 0
    total_start_distance = 0
    for left, right in zip(rows, rows[1:]):
        start_delta = right.lba - left.lba
        gap = right.lba - left.end_lba_exclusive
        total_start_distance += abs(start_delta)
        if gap > 0:
            total_gap += gap
        transitions.append(
            {
                "from": left.name,
                "to": right.name,
                "from_start_lba": f"0x{left.lba:04X}",
                "from_end_lba_exclusive": f"0x{left.end_lba_exclusive:04X}",
                "to_start_lba": f"0x{right.lba:04X}",
                "start_delta_sectors": start_delta,
                "post_transfer_gap_sectors": gap,
            }
        )

    transfer_sectors = sum(item.sectors_touched for item in rows)
    contiguous_start_distance = sum(
        left.sectors_touched for left in rows[:-1]
    )
    return {
        "transfers": [
            {
                "name": item.name,
                "lba": f"0x{item.lba:04X}",
                "sectors_touched": item.sectors_touched,
                "end_lba_exclusive": f"0x{item.end_lba_exclusive:04X}",
            }
            for item in rows
        ],
        "transfer_sectors": transfer_sectors,
        "pure_1x_transfer_seconds": transfer_sectors / 75.0,
        "inter_transfer_gaps_sectors": total_gap,
        "absolute_start_distance_sectors": total_start_distance,
        "contiguous_copy_start_distance_sectors": contiguous_start_distance,
        "avoidable_start_distance_sectors_if_relocated_contiguously": (
            total_start_distance - contiguous_start_distance
        ),
        "transitions": transitions,
    }


def build_scene_seek_report() -> dict[str, object]:
    main = analyze_sequence(MAIN_SCENE)
    alternate = analyze_sequence(ALTERNATE_SCENE)
    return {
        "main_scene": main,
        "alternate_scene": alternate,
        "static_findings": {
            "main_first_gap_sectors": main["transitions"][0][
                "post_transfer_gap_sectors"
            ],
            "main_second_gap_sectors": main["transitions"][1][
                "post_transfer_gap_sectors"
            ],
            "main_total_gap_sectors": main["inter_transfer_gaps_sectors"],
            "main_seek_distance_reduction_sectors": main[
                "avoidable_start_distance_sectors_if_relocated_contiguously"
            ],
            "alternate_total_gap_sectors": alternate[
                "inter_transfer_gaps_sectors"
            ],
        },
        "optimization_architecture": (
            "If ownership-safe free space or an appended/rebuilt data extent is "
            "available, duplicate the three main-scene resources contiguously "
            "and repoint their descriptors. Do not overwrite the 73-sector or "
            "7-sector holes merely because they lie between known resources; "
            "their ownership is not established by this analysis."
        ),
        "interaction_with_selective_restore": (
            "Contiguous relocation optimizes full scene installation. A proven "
            "dialogue-return selective restore would supersede the 0xEE00 VRAM "
            "read on that path and is therefore the higher-value optimization "
            "for repeated interactions."
        ),
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze static seek geometry of hot exploration assets."
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_scene_seek_report()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
