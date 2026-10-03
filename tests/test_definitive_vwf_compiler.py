from __future__ import annotations

import unittest

from cyber_oedo.text.definitive_script_compiler import DefinitiveScriptRow
from cyber_oedo.text.definitive_vwf_compiler import compile_definitive_vwf_mission
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.vwf_cells import VWF_MODE_SIGNATURE
from cyber_oedo.text.vwf_text import derive_vwf_font


def _glyph(*rows: int) -> bytes:
    data = [0] * 16
    for index, value in enumerate(rows, start=5):
        data[index] = value
    return bytes(data)


class DefinitiveVwfCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        bitmaps = {
            "A": _glyph(0x38, 0x44, 0x7C, 0x44, 0x44),
            "I": _glyph(0x20, 0x20, 0x20, 0x20, 0x20),
            " ": bytes(16),
            "?": _glyph(0x38, 0x44, 0x08, 0x00, 0x08),
        }
        characters = "AI ?"
        self.glyphs = EnglishGlyphTable(characters)
        self.font = derive_vwf_font(
            characters,
            tuple(bitmaps[c] for c in characters),
        )

    def test_control_safe_rows_are_promoted_with_one_mission_dictionary(self) -> None:
        first = bytes.fromhex("27 28") + "あ".encode("shift_jis") + b"\x00"
        second = bytes.fromhex("27 28") + "い".encode("shift_jis") + b"\x00"
        second_offset = len(first) + 4
        payload = first + bytes(4) + second

        rows = (
            DefinitiveScriptRow(
                "T90001", "MISSION_TEST", "Spoken dialogue", "TEST1", 0,
                "あ", "AI AI",
            ),
            DefinitiveScriptRow(
                "T90002", "MISSION_TEST", "Spoken dialogue", "TEST2", second_offset,
                "い", "IIIIII",
            ),
        )
        result = compile_definitive_vwf_mission(
            payload,
            rows,
            self.font,
            self.glyphs,
        )
        self.assertEqual(result.vwf_records, 2)
        self.assertEqual(result.fixed_records, 0)
        self.assertGreater(result.dictionary_entries, 0)
        self.assertEqual(len(result.staged_cells), result.dictionary_entries * 32)
        for row in result.rows:
            self.assertEqual(row.status, "vwf_automatic")
            self.assertTrue(row.compiled_record.startswith(bytes.fromhex("27 28") + VWF_MODE_SIGNATURE))


if __name__ == "__main__":
    unittest.main()
