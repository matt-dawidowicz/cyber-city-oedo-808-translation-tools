from __future__ import annotations

import unittest

from cyber_oedo.runtime.native_english_runtime import (
    MISSION0_NATIVE_LAYOUTS,
    STORAGE_CODE_CAPACITY,
    build_mission0_native_runtime_patches,
    build_overlay_runtime,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas


class NativeEnglishRuntimeTests(unittest.TestCase):
    def _fixture(self) -> tuple[EnglishGlyphTable, RasterizedAtlas]:
        text = " ?ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,:;!'"
        glyphs = EnglishGlyphTable(text)
        bitmaps = tuple(
            bytes(((index + row) & 0xFF for row in range(16)))
            for index in range(len(text))
        )
        atlas = RasterizedAtlas(
            characters=text,
            glyphs=bitmaps,
            source_sha256="0" * 64,
            config=RasterConfig(),
        )
        return glyphs, atlas

    def test_repertoire_fits_compact_stock_grid_codes(self) -> None:
        glyphs, _ = self._fixture()
        self.assertLessEqual(len(glyphs.characters), STORAGE_CODE_CAPACITY)

    def test_both_mission0_overlays_build_without_storage_overlap(self) -> None:
        glyphs, atlas = self._fixture()
        for layout in MISSION0_NATIVE_LAYOUTS:
            runtime = build_overlay_runtime(layout, glyphs, atlas)
            self.assertLessEqual(layout.code_cpu + len(runtime.code), layout.font_cpu)
            self.assertIn("parser_dispatch", runtime.labels)
            self.assertIn("glyph_hook", runtime.labels)

    def test_patch_set_covers_parser_font_code_and_atlas_for_each_overlay(self) -> None:
        glyphs, atlas = self._fixture()
        patches = build_mission0_native_runtime_patches(glyphs, atlas)
        self.assertEqual(len(patches), 8)
        labels = [patch.label for patch in patches]
        for layout in MISSION0_NATIVE_LAYOUTS:
            self.assertEqual(sum(label.startswith(layout.label + ":") for label in labels), 4)

    def test_parser_hook_is_exact_cmp_80_source_guard(self) -> None:
        glyphs, atlas = self._fixture()
        patches = build_mission0_native_runtime_patches(glyphs, atlas)
        parser_patches = [patch for patch in patches if "parser trampoline" in patch.label]
        self.assertEqual(len(parser_patches), 2)
        self.assertTrue(all(patch.expected == bytes.fromhex("C9 80 F0") for patch in parser_patches))
        self.assertTrue(all(patch.replacement[0] == 0x4C for patch in parser_patches))


if __name__ == "__main__":
    unittest.main()
