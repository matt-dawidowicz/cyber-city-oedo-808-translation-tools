"""Public CLI facade for the authenticated stock-renderer build."""

from __future__ import annotations

import argparse
import pathlib
from collections.abc import Sequence

from cyber_oedo.build.pipeline import build_human_test_disc
from cyber_oedo.build.plan import PatchPlan, build_profile_plan
from cyber_oedo.build.profiles import mission0_stock as profile
from cyber_oedo.build.verification import verify_plan_footprint


def planned_profile(title_screen_mode: str) -> PatchPlan:
    """Return and independently verify one deterministic patch plan."""

    plan = build_profile_plan(title_screen_mode)
    verify_plan_footprint(plan)
    return plan


def build_parser() -> argparse.ArgumentParser:
    """Build the authenticated human-test command parser."""

    parser = argparse.ArgumentParser(
        description="Build the guarded stock-renderer translation test image."
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument(
        "--title-screen",
        choices=profile.TITLE_SCREEN_MODES,
        default=profile.DEFAULT_TITLE_SCREEN_MODE,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build a verified CloneCD set and print its reviewed footprint."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_human_test_disc(
            args.source_ccd,
            args.output_directory,
            title_screen_mode=args.title_screen,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"output_ccd={result.output_ccd}")
    print(f"profile={result.build_profile}")
    print(f"title_screen={result.title_screen_mode}")
    print(f"text_patches={result.text_patch_count}")
    print(f"binary_patches={result.binary_patch_count}")
    print("changed_relative_sectors=" + ",".join(map(str, result.changed_relative_sectors)))
    print("guarded_relative_sectors=" + ",".join(map(str, result.guarded_relative_sectors)))
    print(f"patch_plan_sha256={result.plan_sha256}")
    print("structural_validation=passed")
    print("human_emulator_test=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
