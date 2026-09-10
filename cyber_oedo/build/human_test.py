"""Public CLI facade for the authenticated stock-renderer build."""

from __future__ import annotations

import argparse
import json
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
        output_ccd = build_human_test_disc(
            args.source_ccd,
            args.output_directory,
            title_screen_mode=args.title_screen,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    manifest = json.loads(
        (output_ccd.parent / "build_manifest.json").read_text(encoding="utf-8")
    )
    changed = manifest["changed_relative_sectors"]
    guarded = manifest["guarded_relative_sectors"]
    print(f"output_ccd={output_ccd}")
    print(f"profile={profile.BUILD_PROFILE}")
    print(f"title_screen={args.title_screen}")
    print(f"text_patches={len(profile.HUMAN_TEST_PATCHES)}")
    print(f"binary_patches={len(manifest['binary_patches'])}")
    print("changed_relative_sectors=" + ",".join(map(str, changed)))
    print("guarded_relative_sectors=" + ",".join(map(str, guarded)))
    print("structural_validation=passed")
    print("human_emulator_test=pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
