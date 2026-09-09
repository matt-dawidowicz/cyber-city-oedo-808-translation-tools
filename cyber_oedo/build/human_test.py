"""Public, explicit API for the authenticated human-test build."""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

from cyber_oedo.build import engine as _engine
from cyber_oedo.build.pipeline import build_human_test_disc
from cyber_oedo.build.plan import PatchPlan, build_profile_plan
from cyber_oedo.build.verification import verify_plan_footprint

BUILD_PROFILE = _engine.BUILD_PROFILE
DEFAULT_TITLE_SCREEN_MODE = _engine.DEFAULT_TITLE_SCREEN_MODE
TITLE_SCREEN_MODES = _engine.TITLE_SCREEN_MODES
OUTPUT_STEM = _engine.OUTPUT_STEM
TRACK2_START_LBA = _engine.TRACK2_START_LBA
HUMAN_TEST_PATCHES = _engine.HUMAN_TEST_PATCHES
HUMAN_TEST_BINARY_PATCHES = _engine.HUMAN_TEST_BINARY_PATCHES
BOOT_MENU_PATCHES = _engine.BOOT_MENU_PATCHES
MISSION_TITLE_PATCHES = _engine.MISSION_TITLE_PATCHES
MISSION0_PROLOGUE_PATCHES = _engine.MISSION0_PROLOGUE_PATCHES
MISSION0_RENDERER_PATCHES = _engine.MISSION0_RENDERER_PATCHES
OPENING_PROFILE_FIELDS = _engine.OPENING_PROFILE_FIELDS
OPENING_PROFILE_TEXT_PATCHES = _engine.OPENING_PROFILE_TEXT_PATCHES
OPENING_PROFILE_LAYOUT_PATCHES = _engine.OPENING_PROFILE_LAYOUT_PATCHES
INFORMATION_SCREEN_LINES = _engine.INFORMATION_SCREEN_LINES
INFORMATION_SCREEN_LAYOUT_PATCHES = (
    _engine.INFORMATION_SCREEN_LAYOUT_PATCHES
)
INFORMATION_HIDDEN_ROW = _engine.INFORMATION_HIDDEN_ROW
PROLOGUE_WRAP_WIDTH = _engine.PROLOGUE_WRAP_WIDTH
TITLE_ASSET_BYTES = _engine.TITLE_ASSET_BYTES
TITLE_PALETTE_OFFSET = _engine.TITLE_PALETTE_OFFSET
TITLE_SCREEN_OFFSET = _engine.TITLE_SCREEN_OFFSET
ascii_to_fullwidth = _engine.ascii_to_fullwidth
wrap_ascii_text = _engine.wrap_ascii_text
optional_title_screen_patches = _engine.optional_title_screen_patches
profile_relative_sectors = _engine.profile_relative_sectors
build_parser = _engine.build_parser


def planned_profile(title_screen_mode: str) -> PatchPlan:
    """Return and independently verify one deterministic patch plan."""

    plan = build_profile_plan(title_screen_mode)
    verify_plan_footprint(plan)
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    """Build an authenticated human-test CloneCD set from CLI arguments."""

    parser = build_parser()
    parser.add_argument(
        "source_ccd",
        type=pathlib.Path,
        help="authenticated source CloneCD .ccd",
    )
    parser.add_argument(
        "output_directory",
        type=pathlib.Path,
        help="new directory for the human-test CloneCD set",
    )
    parser.add_argument(
        "--title-screen",
        choices=TITLE_SCREEN_MODES,
        default=DEFAULT_TITLE_SCREEN_MODE,
    )
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
        (output_ccd.parent / "build_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    changed_relative = manifest["changed_relative_sectors"]
    guarded_relative = manifest["guarded_relative_sectors"]
    changed_absolute = [
        TRACK2_START_LBA + sector
        for sector in changed_relative
    ]
    optional_count = 2 if args.title_screen == "clean" else 0
    print(f"output_ccd={output_ccd}")
    print(f"profile={BUILD_PROFILE}")
    print(f"title_screen={args.title_screen}")
    print(f"text_patches={len(HUMAN_TEST_PATCHES)}")
    print(
        "binary_patches="
        f"{len(HUMAN_TEST_BINARY_PATCHES) + optional_count}"
    )
    print(
        "changed_relative_sectors="
        + ",".join(str(value) for value in changed_relative)
    )
    print(
        "guarded_relative_sectors="
        + ",".join(str(value) for value in guarded_relative)
    )
    print(
        "changed_absolute_lbas="
        + ",".join(str(value) for value in changed_absolute)
    )
    print("structural_validation=passed")
    print("human_emulator_test=pending")
    return 0


__all__ = [
    "BUILD_PROFILE",
    "DEFAULT_TITLE_SCREEN_MODE",
    "TITLE_SCREEN_MODES",
    "OUTPUT_STEM",
    "TRACK2_START_LBA",
    "HUMAN_TEST_PATCHES",
    "HUMAN_TEST_BINARY_PATCHES",
    "BOOT_MENU_PATCHES",
    "MISSION_TITLE_PATCHES",
    "MISSION0_PROLOGUE_PATCHES",
    "MISSION0_RENDERER_PATCHES",
    "OPENING_PROFILE_FIELDS",
    "OPENING_PROFILE_TEXT_PATCHES",
    "OPENING_PROFILE_LAYOUT_PATCHES",
    "INFORMATION_SCREEN_LINES",
    "INFORMATION_SCREEN_LAYOUT_PATCHES",
    "INFORMATION_HIDDEN_ROW",
    "PROLOGUE_WRAP_WIDTH",
    "TITLE_ASSET_BYTES",
    "TITLE_PALETTE_OFFSET",
    "TITLE_SCREEN_OFFSET",
    "ascii_to_fullwidth",
    "wrap_ascii_text",
    "optional_title_screen_patches",
    "profile_relative_sectors",
    "build_parser",
    "planned_profile",
    "build_human_test_disc",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
