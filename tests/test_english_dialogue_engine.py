from __future__ import annotations

import unittest

from cyber_oedo.text.english_dialogue_engine import (
    ENGLISH_GLYPH_BASE,
    ENGLISH_LINE_WIDTH,
    ENGLISH_MODE_SIGNATURE,
    EnglishDialogueCompileError,
    EnglishGlyphTable,
    compile_automatic_record,
    source_requires_manual_anchors,
    wrap_english,
)


class EnglishDialogueEngineTests(unittest.TestCase):
    def test_one_byte_glyph_round_trip(self) -> None:
        table = EnglishGlyphTable.from_texts(("Bartender: Welcome.",))
        encoded = table.encode("Welcome.")
        self.assertEqual(len(encoded), len("Welcome."))
        self.assertTrue(all(value >= ENGLISH_GLYPH_BASE for value in encoded))
        self.assertEqual(table.decode(encoded), "Welcome.")

    def test_wrap_uses_22_character_field(self) -> None:
        self.assertEqual(ENGLISH_LINE_WIDTH, 22)
        lines = wrap_english("First time around here, is it?")
        self.assertTrue(all(len(line) <= 22 for line in lines))
        self.assertEqual(" ".join(lines), "First time around here, is it?")

    def test_source_line_breaks_are_recomputed(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x40,))
            + "犬".encode("shift_jis")
            + bytes((0x21, 0x00))
        )
        text = "Bartender: Welcome to Old City."
        table = EnglishGlyphTable.from_texts((text,))
        compiled = compile_automatic_record(source, text, table)
        self.assertTrue(compiled.startswith(bytes.fromhex("27 28") + ENGLISH_MODE_SIGNATURE))
        self.assertTrue(compiled.endswith(bytes((0x21, 0x00))))
        self.assertNotEqual(compiled, source)

    def test_mid_timed_wait_requires_explicit_anchor(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        self.assertTrue(source_requires_manual_anchors(source))
        table = EnglishGlyphTable.from_texts(("Cat... dog.",))
        with self.assertRaisesRegex(EnglishDialogueCompileError, "anchors"):
            compile_automatic_record(source, "Cat... dog.", table)

    def test_mid_line_advance_does_not_require_anchor(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x40,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        self.assertFalse(source_requires_manual_anchors(source))

    def test_long_unbreakable_word_is_rejected(self) -> None:
        with self.assertRaisesRegex(EnglishDialogueCompileError, "word exceeds"):
            wrap_english("x" * 23)


if __name__ == "__main__":
    unittest.main()
