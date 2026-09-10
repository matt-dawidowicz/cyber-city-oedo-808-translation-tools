"""Architectural invariants for the canonical package layout."""

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
            name for name in RETIRED_ROOT_MODULES if (ROOT / f"{name}.py").exists()
        )
        self.assertEqual([], remaining)


if __name__ == "__main__":
    unittest.main()
