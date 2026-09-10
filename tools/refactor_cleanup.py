#!/usr/bin/env python3
"""One-time mechanical cleanup for the package architecture.

This script is intentionally temporary. It splits the two remaining monolithic
modules from their parsed top-level definitions, converts package imports away
from root compatibility shims, and removes those shims only after canonical
package replacements exist. The cleanup workflow runs the complete synthetic
suite before committing the result.
"""

from __future__ import annotations

import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

ROOT_MODULES = (
    "analyze_text_slots",
    "build_human_test_disc",
    "build_translation_inventory",
    "cdrom_mode1",
    "clonecd_cue",
    "dialogue_relocation",
    "disassemble_huc6280",
    "extract_auxiliary_text",
    "extract_dialogue",
    "extract_track2_mode1",
    "game_layout",
    "make_contact_sheet",
    "pce_graphics",
    "render_pce_tiles",
    "scan_likely_sjis",
    "scan_track",
    "title_logo_mask",
    "title_screen",
    "validate_translation_inventory",
)

IMPORT_REPLACEMENTS = {
    "from cdrom_mode1 import": (
        "from cyber_oedo.disc.cdrom_mode1 import"
    ),
    "from extract_dialogue import": (
        "from cyber_oedo.text.extract_dialogue import"
    ),
    "from game_layout import": (
        "from cyber_oedo.disc.game_layout import"
    ),
    "from pce_graphics import": (
        "from cyber_oedo.graphics.pce_graphics import"
    ),
    "from title_logo_mask import": (
        "from cyber_oedo.graphics.title_logo_mask import"
    ),
    "from title_screen import": (
        "from cyber_oedo.graphics.title_screen import"
    ),
}


def _node_name(node: ast.AST) -> str | None:
    """Return the public name defined by one top-level syntax node."""

    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target.id
    return None


def _definition_map(source: str) -> dict[str, ast.AST]:
    """Index named top-level definitions in source order."""

    tree = ast.parse(source)
    result: dict[str, ast.AST] = {}
    for node in tree.body:
        name = _node_name(node)
        if name is not None:
            result[name] = node
    return result


def _render_nodes(source: str, names: tuple[str, ...]) -> str:
    """Render selected top-level definitions in requested order."""

    nodes = _definition_map(source)
    missing = [name for name in names if name not in nodes]
    if missing:
        raise RuntimeError(f"missing definitions: {missing}")
    return "\n\n\n".join(ast.unparse(nodes[name]) for name in names) + "\n"


def _write_module(
    path: pathlib.Path,
    docstring: str,
    imports: str,
    body: str,
) -> None:
    """Write one generated Python module with a small explicit header."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'"""{docstring}"""\n\n'
        "from __future__ import annotations\n\n"
        f"{imports.strip()}\n\n\n"
        f"{body.rstrip()}\n",
        encoding="utf-8",
    )


def _canonicalize_package_imports() -> None:
    """Replace remaining package-to-root imports with package paths."""

    for path in (ROOT / "cyber_oedo").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in IMPORT_REPLACEMENTS.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _split_engine() -> None:
    """Split the 91 KiB build engine into typed profile modules."""

    engine_path = ROOT / "cyber_oedo" / "build" / "engine.py"
    if not engine_path.exists():
        return
    source = engine_path.read_text(encoding="utf-8")
    profiles = ROOT / "cyber_oedo" / "build" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    (profiles / "__init__.py").write_text(
        '"""Immutable translation/build profile definitions."""\n',
        encoding="utf-8",
    )

    model_names = (
        "InPlaceTextPatch",
        "InformationScreenLine",
        "OpeningProfileField",
        "wrap_ascii_text",
        "ascii_to_fullwidth",
    )
    _write_module(
        profiles / "models.py",
        "Typed, same-size text and row-layout patch models.",
        "from dataclasses import dataclass\n"
        "from cyber_oedo.disc.cdrom_mode1 import PayloadPatch",
        _render_nodes(source, model_names),
    )

    startup_names = (
        "PROLOGUE_WRAP_WIDTH",
        "BOOT_MENU_PATCHES",
        "STARTUP_V2_EXTRA_PATCHES",
        "MISSION_TITLE_PATCHES",
        "MISSION0_DIALOGUE_PATCHES",
        "MISSION0_PROLOGUE_PATCHES",
    )
    _write_module(
        profiles / "startup.py",
        "Startup, mission-title, and Mission 0 stock-renderer text data.",
        "from cyber_oedo.build.profiles.models import InPlaceTextPatch",
        _render_nodes(source, startup_names),
    )

    media_names = (
        "INFORMATION_HIDDEN_ROW",
        "INFORMATION_SCREEN_LINES",
        "INFORMATION_SCREEN_TEXT_PATCHES",
        "INFORMATION_SCREEN_LAYOUT_PATCHES",
    )
    _write_module(
        profiles / "media_mix.py",
        "Media Mix text and row-layout profile data.",
        "from cyber_oedo.build.profiles.models import InformationScreenLine",
        _render_nodes(source, media_names),
    )

    dossier_names = (
        "OPENING_PROFILE_FIELDS",
        "OPENING_PROFILE_TEXT_PATCHES",
        "OPENING_PROFILE_LAYOUT_PATCHES",
    )
    _write_module(
        profiles / "dossiers.py",
        "Opening criminal-dossier text and row-layout profile data.",
        "from cyber_oedo.build.profiles.media_mix import INFORMATION_HIDDEN_ROW\n"
        "from cyber_oedo.build.profiles.models import OpeningProfileField",
        _render_nodes(source, dossier_names),
    )

    profile_names = (
        "BUILD_PROFILE",
        "OUTPUT_STEM",
        "TITLE_SCREEN_OFFSET",
        "TITLE_PALETTE_OFFSET",
        "TITLE_SCREEN_MODES",
        "DEFAULT_TITLE_SCREEN_MODE",
        "TITLE_SCREEN_SOURCE_SHA256",
        "TITLE_PALETTE_SOURCE_SHA256",
        "SOURCE_HASHES",
        "HUMAN_TEST_PATCHES",
        "MISSION0_RENDERER_PATCHES",
        "HUMAN_TEST_BINARY_PATCHES",
        "optional_title_screen_patches",
        "relative_sectors_for_patches",
        "profile_relative_sectors",
        "build_tester_readme",
    )
    profile_imports = """
import hashlib
import pathlib

from cyber_oedo.build.profiles.dossiers import (
    OPENING_PROFILE_FIELDS,
    OPENING_PROFILE_LAYOUT_PATCHES,
    OPENING_PROFILE_TEXT_PATCHES,
)
from cyber_oedo.build.profiles.media_mix import (
    INFORMATION_HIDDEN_ROW,
    INFORMATION_SCREEN_LAYOUT_PATCHES,
    INFORMATION_SCREEN_LINES,
    INFORMATION_SCREEN_TEXT_PATCHES,
)
from cyber_oedo.build.profiles.models import (
    InPlaceTextPatch,
    InformationScreenLine,
    OpeningProfileField,
    ascii_to_fullwidth,
    wrap_ascii_text,
)
from cyber_oedo.build.profiles.startup import (
    BOOT_MENU_PATCHES,
    MISSION0_DIALOGUE_PATCHES,
    MISSION0_PROLOGUE_PATCHES,
    MISSION_TITLE_PATCHES,
    PROLOGUE_WRAP_WIDTH,
    STARTUP_V2_EXTRA_PATCHES,
)
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch, read_payload_range
from cyber_oedo.disc.game_layout import (
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)
from cyber_oedo.graphics.title_screen import (
    TITLE_ASSET_BYTES,
    TITLE_PALETTE_BYTES,
    build_clean_title_asset,
    build_grayscale_title_palette_cycle,
)
"""
    _write_module(
        profiles / "mission0_stock.py",
        "Assemble the maintained stock-renderer human-test build profile.",
        profile_imports,
        _render_nodes(source, profile_names),
    )

    engine_path.write_text(
        '"""Compatibility namespace for the decomposed stock build profile."""\n\n'
        "from cyber_oedo.build.profiles.mission0_stock import *  # noqa: F403\n",
        encoding="utf-8",
    )

    for relative in (
        "cyber_oedo/build/pipeline.py",
        "cyber_oedo/build/plan.py",
        "cyber_oedo/build/verification.py",
    ):
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "from cyber_oedo.build import engine",
            "from cyber_oedo.build.profiles import mission0_stock as profile",
        ).replace("engine.", "profile.")
        path.write_text(text, encoding="utf-8")

    human_test = ROOT / "cyber_oedo" / "build" / "human_test.py"
    human_test.write_text(
        '''"""Public CLI facade for the authenticated stock-renderer build."""

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
        (output_ccd.parent / "build_manifest.json").read_text(
            encoding="utf-8"
        )
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
''',
        encoding="utf-8",
    )


def _split_relocation() -> None:
    """Separate text layout from pointer/storage relocation mechanics."""

    path = ROOT / "cyber_oedo" / "text" / "dialogue_relocation.py"
    if not path.exists():
        return
    source = path.read_text(encoding="utf-8")

    layout_names = (
        "DIALOGUE_MARKER",
        "DIALOGUE_TERMINATOR",
        "PAGE_CONTROL",
        "STOCK_LINE_WIDTH",
        "ascii_to_fullwidth_sjis",
        "wrap_english_lines",
        "PageGeometry",
        "DialoguePage",
        "wrap_dialogue_page",
        "PageBreakPlan",
    )
    _write_module(
        ROOT / "cyber_oedo" / "text" / "layout.py",
        "Stock-renderer English encoding, wrapping, and page compilation.",
        "from dataclasses import dataclass\n"
        "from cyber_oedo.text.extract_dialogue import parse_record",
        _render_nodes(source, layout_names),
    )

    relocation_names = (
        "PointerSite",
        "RelocationArea",
        "DialogueRelocationPlan",
    )
    optimized_scan = '''
def find_u16_pointer_candidates(
    data: bytes,
    target_offset: int,
    base_offset: int,
    search_start: int,
    search_end: int,
    *,
    alignment: int = 1,
) -> tuple[int, ...]:
    """Find aligned byte candidates without a Python byte-by-byte scan."""

    if alignment <= 0:
        raise ValueError("pointer search alignment must be positive")
    if not 0 <= search_start <= search_end <= len(data):
        raise ValueError("pointer search bounds are outside the data")
    encoded_value = target_offset - base_offset
    if not 0 <= encoded_value <= 0xFFFF:
        raise ValueError("candidate target is outside the 16-bit window")
    needle = encoded_value.to_bytes(2, "little")
    matches: list[int] = []
    offset = data.find(needle, search_start, search_end)
    while offset >= 0:
        if (offset - search_start) % alignment == 0:
            matches.append(offset)
        offset = data.find(needle, offset + 1, search_end)
    return tuple(matches)
'''
    _write_module(
        ROOT / "cyber_oedo" / "text" / "relocation.py",
        "Guarded pointer and owned-storage relocation models.",
        "from dataclasses import dataclass\n"
        "from cyber_oedo.disc.cdrom_mode1 import PayloadPatch",
        _render_nodes(source, relocation_names) + optimized_scan,
    )

    path.write_text(
        '''"""Compatibility facade for split stock-layout and relocation APIs."""

from cyber_oedo.text.layout import (
    DIALOGUE_MARKER,
    DIALOGUE_TERMINATOR,
    PAGE_CONTROL,
    STOCK_LINE_WIDTH,
    DialoguePage,
    PageBreakPlan,
    PageGeometry,
    ascii_to_fullwidth_sjis,
    wrap_dialogue_page,
    wrap_english_lines,
)
from cyber_oedo.text.relocation import (
    DialogueRelocationPlan,
    PointerSite,
    RelocationArea,
    find_u16_pointer_candidates,
)

__all__ = [
    "DIALOGUE_MARKER",
    "DIALOGUE_TERMINATOR",
    "PAGE_CONTROL",
    "STOCK_LINE_WIDTH",
    "DialoguePage",
    "PageBreakPlan",
    "PageGeometry",
    "ascii_to_fullwidth_sjis",
    "wrap_dialogue_page",
    "wrap_english_lines",
    "DialogueRelocationPlan",
    "PointerSite",
    "RelocationArea",
    "find_u16_pointer_candidates",
]
''',
        encoding="utf-8",
    )


def _remove_root_shims() -> None:
    """Delete every historical top-level Python compatibility module."""

    for module in ROOT_MODULES:
        path = ROOT / f"{module}.py"
        if path.exists():
            path.unlink()

    pyproject = ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    start = text.find("# Temporary shims still required")
    if start >= 0:
        end = text.index("[tool.setuptools.packages.find]", start)
        text = (
            text[:start]
            + "[tool.setuptools]\ninclude-package-data = true\n\n"
            + text[end:]
        )
        pyproject.write_text(text, encoding="utf-8")

    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        requirements.unlink()
    manifest = ROOT / "MANIFEST.in"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "include requirements.txt\n",
            "",
        ),
        encoding="utf-8",
    )


def _write_architecture_test() -> None:
    """Add a regression test forbidding package imports from root shims."""

    path = ROOT / "tests" / "test_architecture.py"
    path.write_text(
        '''"""Architectural invariants for the canonical package layout."""

from __future__ import annotations

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RETIRED_ROOT_MODULES = {
    "analyze_text_slots",
    "build_human_test_disc",
    "build_translation_inventory",
    "cdrom_mode1",
    "clonecd_cue",
    "dialogue_relocation",
    "disassemble_huc6280",
    "extract_auxiliary_text",
    "extract_dialogue",
    "extract_track2_mode1",
    "game_layout",
    "make_contact_sheet",
    "pce_graphics",
    "render_pce_tiles",
    "scan_likely_sjis",
    "scan_track",
    "title_logo_mask",
    "title_screen",
    "validate_translation_inventory",
}


class PackageArchitectureTests(unittest.TestCase):
    """Prevent the transitional root-module architecture from returning."""

    def test_package_does_not_import_retired_root_modules(self) -> None:
        """Require every internal import to resolve through cyber_oedo."""

        failures: list[str] = []
        for path in (ROOT / "cyber_oedo").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in RETIRED_ROOT_MODULES:
                            failures.append(f"{path}: {alias.name}")
                if module in RETIRED_ROOT_MODULES:
                    failures.append(f"{path}: {module}")
        self.assertEqual([], failures)

    def test_retired_root_modules_are_absent(self) -> None:
        """Keep source-tree compatibility shims out of the repository."""

        remaining = sorted(
            name
            for name in RETIRED_ROOT_MODULES
            if (ROOT / f"{name}.py").exists()
        )
        self.assertEqual([], remaining)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


def main() -> None:
    """Apply the one-time cleanup deterministically."""

    marker = ROOT / "cyber_oedo" / "build" / "profiles" / "mission0_stock.py"
    if marker.exists():
        print("cleanup refactor already applied")
        return
    _canonicalize_package_imports()
    _split_engine()
    _split_relocation()
    _canonicalize_package_imports()
    _remove_root_shims()
    _write_architecture_test()
    print("cleanup refactor applied")


if __name__ == "__main__":
    main()
