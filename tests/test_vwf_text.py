from __future__ import annotations

import unittest

from cyber_oedo.text.vwf_text import (
    LINE_TILE_BYTES_4BPP,
    character_delta_tiles,
    derive_vwf_font,
    measure_text,
    paginate_vwf,
    render_line,
    wrap_vwf,
)


def _glyph(*rows: int) -> bytes:
    data = [0] * 16
    for index, value in enumerate(rows, start=5):
        data[index] = value
    return bytes(data)


class VwfTextTests(unittest.TestCase):
    def setUp(self) -> None:
        a = _glyph(0x38, 0x44, 0x7C, 0x44, 0x44)
        i = _glyph(0x20, 0x20, 0x20, 0x20, 0x20)
        space = bytes(16)
        self.font = derive_vwf_font("AI ", (a, i, space))

    def test_metrics_are_derived_from_visible_columns(self) -> None:
        self.assertEqual(self.font.metric("A").width, 5)
        self.assertEqual(self.font.metric("A").advance, 6)
        self.assertEqual(self.font.metric("I").width, 1)
        self.assertEqual(self.font.metric(" ").advance, 4)

    def test_measurement_is_proportional(self) -> None:
        self.assertGreater(measure_text("AA", self.font), measure_text("II", self.font))

    def test_wrap_uses_pixel_width_not_character_count(self) -> None:
        lines = wrap_vwf("AI AI AI AI AI AI AI", self.font, max_pixels=30)
        self.assertEqual(lines, ("AI AI", "AI AI", "AI AI", "AI"))

    def test_line_compiles_to_pce_tile_strip(self) -> None:
        line = render_line("AI AI", self.font)
        self.assertEqual(len(line.tile_bytes_4bpp), LINE_TILE_BYTES_4BPP)
        self.assertEqual(line.pixel_width, 19)
        self.assertEqual(len(line.character_end_pixels), len(line.text))

    def test_reveal_map_only_touches_crossed_tile_columns(self) -> None:
        line = render_line("AI AI", self.font)
        deltas = character_delta_tiles(line)
        self.assertEqual(deltas[0], (0,))
        self.assertIn(2, deltas[-2])

    def test_pagination_caps_three_lines(self) -> None:
        pages = paginate_vwf(
            "AI AI AI AI AI AI AI AI AI AI AI AI AI",
            self.font,
            max_pixels=30,
        )
        self.assertTrue(all(1 <= len(page.lines) <= 3 for page in pages))
        self.assertGreater(len(pages), 1)


if __name__ == "__main__":
    unittest.main()
