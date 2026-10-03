from __future__ import annotations

import unittest

from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.vwf_cells import (
    MAX_CELL_GLYPHS,
    VWF_CELLS_PER_LINE,
    VWF_DESCRIPTOR_BYTES,
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VWF_TOKEN_FIRST_MAX,
    VWF_TOKEN_FIRST_MIN,
    VwfCellDescriptor,
    compile_vwf_corpus,
    compile_vwf_text,
    decode_vwf_token,
    encode_vwf_token,
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

    def test_tokens_are_self_identifying_after_stock_redraw_storage(self) -> None:
        for token in (0, 255, 256, 2048):
            raw = encode_vwf_token(token)
            self.assertGreaterEqual(raw[0], VWF_TOKEN_FIRST_MIN)
            self.assertLessEqual(raw[0], VWF_TOKEN_FIRST_MAX)
            self.assertEqual(decode_vwf_token(raw), token)


    def test_cell_tokens_round_trip_every_visible_character(self) -> None:
        result = compile_vwf_text("AI AI AI AI AI AI", self.font, self.table)
        reverse = {value - 0x80: key for key, value in self.table.char_to_byte.items()}
        for line in result.lines:
            rebuilt = ""
            for token in line.tokens:
                descriptor = result.dictionary.descriptors[token]
                rebuilt += "".join(reverse[glyph_id] for glyph_id in descriptor.glyph_ids)
            self.assertEqual(rebuilt, line.text)

    def test_mission_corpus_uses_one_shared_dictionary(self) -> None:
        first, second = compile_vwf_corpus(
            ("AI AI", "IIIIII"),
            self.font,
            self.table,
        )
        self.assertEqual(first.dictionary, second.dictionary)
        self.assertGreater(len(first.dictionary.descriptors), 1)
        for compiled in (first, second):
            for line in compiled.lines:
                self.assertTrue(
                    all(token < len(compiled.dictionary.descriptors) for token in line.tokens)
                )

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
