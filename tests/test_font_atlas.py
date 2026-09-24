from __future__ import annotations

import unittest

from cyber_oedo.text.font_atlas import (
    GLYPH_BYTES,
    PAIR_CELL_BYTES,
    FontAtlasError,
    RasterizedAtlas,
    compose_pair_cell,
    compose_pair_from_atlas,
    split_pair_cell,
)


class FontAtlasTests(unittest.TestCase):
    def test_pair_cell_interleaves_sixteen_rows(self) -> None:
        left = bytes(range(16))
        right = bytes(range(0x80, 0x90))
        cell = compose_pair_cell(left, right)
        self.assertEqual(len(cell), PAIR_CELL_BYTES)
        self.assertEqual(cell[:6], bytes((0x00, 0x80, 0x01, 0x81, 0x02, 0x82)))
        self.assertEqual(split_pair_cell(cell), (left, right))

    def test_solid_halves_fill_expected_side_bytes(self) -> None:
        left = bytes([0xFF]) * GLYPH_BYTES
        right = bytes([0x00]) * GLYPH_BYTES
        cell = compose_pair_cell(left, right)
        self.assertEqual(cell, bytes((0xFF, 0x00)) * 16)

    def test_invalid_glyph_length_is_rejected(self) -> None:
        with self.assertRaisesRegex(FontAtlasError, "8x16 glyph"):
            compose_pair_cell(b"\x00" * 15, b"\x00" * 16)

    def test_atlas_pair_uses_one_byte_glyph_ids(self) -> None:
        atlas = RasterizedAtlas(
            characters=" A",
            glyphs=(bytes([0x00]) * 16, bytes([0xAA]) * 16),
            source_sha256="00" * 32,
            config=__import__(
                "cyber_oedo.text.font_atlas",
                fromlist=["RasterConfig"],
            ).RasterConfig(),
        )
        cell = compose_pair_from_atlas(atlas, 1, 0)
        self.assertEqual(cell, bytes((0xAA, 0x00)) * 16)

    def test_split_requires_stock_32_byte_cell(self) -> None:
        with self.assertRaisesRegex(FontAtlasError, "32 bytes"):
            split_pair_cell(b"\x00" * 31)


if __name__ == "__main__":
    unittest.main()
