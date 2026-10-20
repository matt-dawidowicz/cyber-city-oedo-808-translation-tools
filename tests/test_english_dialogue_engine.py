from __future__ import annotations

import unittest

from cyber_oedo.text.english_dialogue_engine import (
    ENGLISH_GLYPH_BASE,
    ENGLISH_LINE_WIDTH,
    ENGLISH_MODE_SIGNATURE,
    ENGLISH_SEGMENT_END,
    EnglishDialogueCompileError,
    EnglishGlyphTable,
    compile_anchored_record,
    compile_automatic_record,
    compile_paced_record,
    pacing_split_points,
    encode_english_segment,
    source_requires_manual_anchors,
    wrap_english,
)


class EnglishDialogueEngineTests(unittest.TestCase):
    def test_one_byte_glyph_round_trip(self) -> None:
        table = EnglishGlyphTable.from_texts(("Bartender: Welcome.?",))
        encoded = table.encode("Welcome.")
        self.assertEqual(len(encoded), len("Welcome."))
        self.assertTrue(all(value >= ENGLISH_GLYPH_BASE for value in encoded))
        self.assertEqual(table.decode(encoded), "Welcome.")

    def test_segment_is_self_contained(self) -> None:
        table = EnglishGlyphTable.from_texts(("Hi?",))
        segment = encode_english_segment("Hi", table)
        self.assertTrue(segment.startswith(ENGLISH_MODE_SIGNATURE))
        self.assertEqual(segment[-1], ENGLISH_SEGMENT_END)
        self.assertEqual(table.decode(segment[2:-1]), "Hi")

    def test_wrap_uses_22_character_field(self) -> None:
        self.assertEqual(ENGLISH_LINE_WIDTH, 22)
        lines = wrap_english("First time around here, is it?")
        self.assertTrue(all(len(line) <= 22 for line in lines))
        self.assertEqual(" ".join(lines), "First time around here, is it?")

    def test_source_line_breaks_are_recomputed_as_stock_controls(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x40,))
            + "犬".encode("shift_jis")
            + bytes((0x21, 0x00))
        )
        text = "Bartender: Welcome to Old City."
        table = EnglishGlyphTable.from_texts((text + "?",))
        compiled = compile_automatic_record(source, text, table)
        self.assertTrue(compiled.startswith(bytes.fromhex("27 28") + ENGLISH_MODE_SIGNATURE))
        self.assertIn(bytes((ENGLISH_SEGMENT_END, 0x40)) + ENGLISH_MODE_SIGNATURE, compiled)
        self.assertTrue(compiled.endswith(bytes((ENGLISH_SEGMENT_END, 0x21, 0x00))))
        self.assertNotEqual(compiled, source)

    def test_timed_waits_can_be_reanchored_as_pacing(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        text = "Wait here, then go."
        table = EnglishGlyphTable.from_texts((text + "?",))
        points = pacing_split_points(source, text)
        self.assertEqual(len(points), 1)
        compiled = compile_paced_record(source, text, table)
        self.assertEqual(compiled.count(bytes((0x2F,))), 1)
        self.assertIn(
            bytes((ENGLISH_SEGMENT_END, 0x2F)) + ENGLISH_MODE_SIGNATURE,
            compiled,
        )

    def test_legacy_pacing_wrap_carries_column_across_wait(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        english = "ABCDEFGHIJ KLMNOPQRSTUVWXYZabcd"
        glyphs = EnglishGlyphTable.from_texts((english,))
        compiled = compile_paced_record(source, english, glyphs)
        # The 20-character second phrase starts on a new line; the pause
        # itself must not be mistaken for a cursor or page advance.
        self.assertEqual(compiled.count(bytes((0x2F,))), 1)
        self.assertEqual(compiled.count(bytes((0x40,))), 1)
        self.assertIn(
            bytes((ENGLISH_SEGMENT_END, 0x2F, 0x40)) + ENGLISH_MODE_SIGNATURE,
            compiled,
        )

    def test_mid_timed_wait_requires_explicit_anchor(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        self.assertTrue(source_requires_manual_anchors(source))
        table = EnglishGlyphTable.from_texts(("Cat... dog.?",))
        with self.assertRaisesRegex(EnglishDialogueCompileError, "anchors"):
            compile_automatic_record(source, "Cat... dog.", table)

    def test_anchored_record_preserves_semantic_control_byte_for_byte(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        table = EnglishGlyphTable.from_texts(("Wait... go!?",))
        compiled = compile_anchored_record(
            source,
            ("Wait...", "go!"),
            table,
        )
        self.assertEqual(compiled.count(bytes((0x2F,))), 1)
        self.assertIn(
            bytes((ENGLISH_SEGMENT_END, 0x2F)) + ENGLISH_MODE_SIGNATURE,
            compiled,
        )
        self.assertTrue(compiled.endswith(bytes((ENGLISH_SEGMENT_END, 0x00))))

    def test_anchored_record_rejects_wrong_fragment_count(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "猫".encode("shift_jis")
            + bytes((0x2F,))
            + "犬".encode("shift_jis")
            + bytes((0x00,))
        )
        table = EnglishGlyphTable.from_texts(("Only one?",))
        with self.assertRaisesRegex(EnglishDialogueCompileError, "one more"):
            compile_anchored_record(source, ("Only one",), table)

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
