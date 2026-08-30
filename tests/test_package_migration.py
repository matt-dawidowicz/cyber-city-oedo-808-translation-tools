"""Verify package ownership while preserving historical import paths."""

from __future__ import annotations

import importlib
import unittest


class CompatibilityShimTests(unittest.TestCase):
    """Ensure root modules re-export packaged implementation objects."""

    def assert_same_symbol(
        self,
        root_name: str,
        package_name: str,
        symbol: str,
    ) -> None:
        """Assert one historical symbol is the packaged object itself."""

        root = importlib.import_module(root_name)
        package = importlib.import_module(package_name)
        self.assertIs(getattr(root, symbol), getattr(package, symbol))

    def test_disc_cluster(self) -> None:
        """Keep layout and raw-sector compatibility imports exact."""

        self.assert_same_symbol(
            "game_layout",
            "cyber_oedo.disc.game_layout",
            "SECTOR_SIZE",
        )
        self.assert_same_symbol(
            "cdrom_mode1",
            "cyber_oedo.disc.cdrom_mode1",
            "PayloadPatch",
        )

    def test_text_cluster(self) -> None:
        """Keep dialogue compatibility imports exact."""

        self.assert_same_symbol(
            "extract_dialogue",
            "cyber_oedo.text.extract_dialogue",
            "parse_record",
        )
        self.assert_same_symbol(
            "dialogue_relocation",
            "cyber_oedo.text.dialogue_relocation",
            "DialoguePage",
        )

    def test_graphics_cluster(self) -> None:
        """Keep graphics compatibility imports exact."""

        self.assert_same_symbol(
            "pce_graphics",
            "cyber_oedo.graphics.pce_graphics",
            "encode_tile",
        )
        self.assert_same_symbol(
            "title_screen",
            "cyber_oedo.graphics.title_screen",
            "build_clean_title_asset",
        )

    def test_analysis_cluster(self) -> None:
        """Keep analysis compatibility imports exact."""

        self.assert_same_symbol(
            "disassemble_huc6280",
            "cyber_oedo.analysis.disassemble_huc6280",
            "decode_instruction",
        )

    def test_experimental_cluster(self) -> None:
        """Keep Stage 1 compatibility imports exact."""

        self.assert_same_symbol(
            "wide_runtime_stage1",
            "cyber_oedo.experimental.wide_runtime_stage1",
            "RuntimePatch",
        )


if __name__ == "__main__":
    unittest.main()
