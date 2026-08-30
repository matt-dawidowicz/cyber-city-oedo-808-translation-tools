"""Public authenticated human-test build facade and compatibility surface."""

from __future__ import annotations

import json
import pathlib

from cyber_oedo.build import engine as _engine
from cyber_oedo.build.plan import PatchPlan, build_profile_plan
from cyber_oedo.build.verification import verify_plan_footprint


globals().update(
    {
        name: value
        for name, value in vars(_engine).items()
        if not name.startswith("__")
    }
)


def planned_profile(title_screen_mode: str) -> PatchPlan:
    """Return and independently verify the selected hash-only patch plan."""

    plan = build_profile_plan(title_screen_mode)
    verify_plan_footprint(plan)
    return plan


def build_human_test_disc(
    source_ccd: pathlib.Path,
    output_directory: pathlib.Path,
    *,
    title_screen_mode: str = _engine.DEFAULT_TITLE_SCREEN_MODE,
) -> pathlib.Path:
    """Preflight the deterministic plan, then run the authenticated engine.

    Args:
        source_ccd: Authenticated source CloneCD descriptor.
        output_directory: New directory that will receive the completed set.
        title_screen_mode: ``"clean"`` or ``"original"``.

    Returns:
        Final output CCD path returned by the unchanged build engine.

    Raises:
        OSError: Propagated from authenticated source/build operations.
        ValueError: Propagated from plan or build verification failures.

    Side Effects:
        Performs the same isolated CloneCD copy, patch, and verification
        workflow as the preserved build engine after a source-independent plan
        consistency check.
    """

    planned_profile(title_screen_mode)
    return _engine.build_human_test_disc(
        source_ccd,
        output_directory,
        title_screen_mode=title_screen_mode,
    )


def main() -> None:
    """Run the historical builder CLI through the decomposed facade."""

    parser = _engine.build_parser()
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
        choices=_engine.TITLE_SCREEN_MODES,
        default=_engine.DEFAULT_TITLE_SCREEN_MODE,
        help=(
            "opening graphic variant: antialiased generated title and "
            "grayscale palette, or untouched original (default: clean)"
        ),
    )
    args = parser.parse_args()
    try:
        output_ccd = build_human_test_disc(
            args.source_ccd,
            args.output_directory,
            title_screen_mode=args.title_screen,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    manifest_path = output_ccd.parent / "build_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_relative = manifest["changed_relative_sectors"]
    guarded_relative = manifest["guarded_relative_sectors"]
    changed_absolute = [
        _engine.TRACK2_START_LBA + sector
        for sector in changed_relative
    ]
    optional_count = 2 if args.title_screen == "clean" else 0
    print(f"output_ccd={output_ccd}")
    print(f"profile={_engine.BUILD_PROFILE}")
    print(f"title_screen={args.title_screen}")
    print(f"text_patches={len(_engine.HUMAN_TEST_PATCHES)}")
    print(
        "binary_patches="
        f"{len(_engine.HUMAN_TEST_BINARY_PATCHES) + optional_count}"
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
