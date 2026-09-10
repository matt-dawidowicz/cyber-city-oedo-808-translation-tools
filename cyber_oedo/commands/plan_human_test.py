"""Emit a dry-run human-test patch plan without opening a disc image."""

from __future__ import annotations

import argparse
import json
import pathlib
from collections.abc import Sequence

from cyber_oedo.build.human_test import planned_profile
from cyber_oedo.contracts import BUILD_PLAN_V1


def build_payload(title_screen_mode: str) -> dict[str, object]:
    """Return versioned JSON data for one source-independent build plan."""

    plan = planned_profile(title_screen_mode)
    category_counts: dict[str, int] = {}
    for entry in plan.entries:
        category_counts[entry.category] = category_counts.get(entry.category, 0) + 1
    return {
        "contract": BUILD_PLAN_V1.identifier,
        "schema_version": BUILD_PLAN_V1.version,
        "plan_sha256": plan.sha256(),
        "profile": {
            "name": plan.build_profile,
            "title_screen_mode": plan.title_screen_mode,
            "patch_count": len(plan.entries),
            "category_counts": category_counts,
            "guarded_sector_count": len(plan.guarded_relative_sectors),
        },
        "plan": plan.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    """Build the no-disc dry-run command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Describe the complete guarded human-test patch plan "
            "without opening or writing a disc image."
        )
    )
    parser.add_argument(
        "--title-screen",
        choices=("clean", "original"),
        default="clean",
        help="select the planned title-screen variant",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="optional JSON output path; defaults to standard output",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit compact JSON instead of indented JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Write or print a deterministic source-independent patch plan."""

    args = build_parser().parse_args(argv)
    indent = None if args.compact else 2
    text = (
        json.dumps(
            build_payload(args.title_screen),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
        )
        + "\n"
    )
    if args.output is None:
        print(text, end="")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
