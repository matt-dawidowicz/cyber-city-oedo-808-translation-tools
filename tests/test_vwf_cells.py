from __future__ import annotations

import unittest

from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.vwf_cells import (
    MAX_CELL_GLYPHS,
    VWF_CELLS_PER_LINE,
    VWF_DESCRIPTOR_BYTES,
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VwfCellDescriptor,
    compile_vwf_text,
)
from cyber_oedo.text.vwf_text import derive_vwf_font


def _glyph(*rows: int) -> bytes:
    data = [0] * 16
    for index, value in enumerate(rows, start=5):
        data[index] = value
    return bytes(data)


class VwfCellTests(unittest.TestCase):
    def setUp(self) -> None:
        glyphs = {
            "A": _glyph(0x38, 0x44, 0x7C, 0x44, 0x44),
            "I": _glyph(0x20, 0x20, 0x20, 0x20, 0x20),
            " ": bytes(16),
            "?": _glyph(0x38, 0x44, 0x08, 0x00, 0x08),
        }
        characters = "AI ?"
        self.table = EnglishGlyphTable(characters)
        self.font = derive_vwf_font(characters, tuple(glyphs[c] for c in characters))

    def test_descriptor_is_fixed_width(self) -> None:
        row = VwfCellDescriptor((0, 1), 8)
        self.assertEqual(len(row.encode()), VWF_DESCRIPTOR_BYTES)
        self.assertEqual(row.encode()[0], 2)

    def test_compiler_preserves_stock_cell_budget(self) -> None:
        result = compile_vwf_text("AI AI AI AI AI AI", self.font, self.table)
        self.assertTrue(result.lines)
        self.assertTrue(
            all(len(line.tokens) <= VWF_CELLS_PER_LINE for line in result.lines)
        )

    def test_stream_uses_vwf_signature_and_ffff_terminator(self) -> None:
        result = compile_vwf_text("AI AI", self.font, self.table)
        stream = result.stream
        self.assertTrue(stream.startswith(VWF_MODE_SIGNATURE))
        self.assertIn(VWF_SEGMENT_END_TOKEN.to_bytes(2, "little"), stream)

    def test_dictionary_deduplicates_repeated_cells(self) -> None:
        result = compile_vwf_text("AI AI AI", self.font, self.table)
        tokens = result.lines[0].tokens
        self.assertLessEqual(len(result.dictionary.descriptors), len(tokens))

    def test_long_narrow_runs_may_pack_more_than_two_glyphs(self) -> None:
        result = compile_vwf_text("IIIIII", self.font, self.table)
        self.assertEqual(len(result.lines), 1)
        # Proportional I is narrow enough to demonstrate the VWF advantage.
        self.assertLess(len(result.lines[0].tokens), 3)
        self.assertLessEqual(
            max(len(d.glyph_ids) for d in result.dictionary.descriptors),
            MAX_CELL_GLYPHS,
        )


if __name__ == "__main__":
    unittest.main()
