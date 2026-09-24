from __future__ import annotations

import unittest

from cyber_oedo.text.packed_english import (
    DEFAULT_DISPLAY_CHARACTERS,
    PRIVATE_LEADS,
    PRIVATE_TOKEN_CAPACITY,
    PRIVATE_TRAILS,
    GlyphRepertoire,
    PackedEnglishDictionary,
    PackedEnglishError,
    private_index_from_token,
    private_token_for_index,
)


class PackedEnglishTests(unittest.TestCase):
    def test_private_namespace_has_expected_capacity(self) -> None:
        self.assertEqual(len(PRIVATE_LEADS), 13)
        self.assertEqual(len(PRIVATE_TRAILS), 188)
        self.assertEqual(PRIVATE_TOKEN_CAPACITY, 2444)

    def test_private_token_index_round_trip(self) -> None:
        for index in (0, 1, 187, 188, 1024, PRIVATE_TOKEN_CAPACITY - 1):
            token = private_token_for_index(index)
            self.assertEqual(len(token), 2)
            self.assertIn(token[0], PRIVATE_LEADS)
            self.assertIn(token[1], PRIVATE_TRAILS)
            self.assertEqual(private_index_from_token(token), index)

    def test_private_lead_can_never_be_dialogue_control_byte(self) -> None:
        controls = {0x00, 0x21, 0x2A, 0x2F, 0x3D, 0x40, 0x5C, 0x7E}
        self.assertTrue(all(lead > 0x80 for lead in PRIVATE_LEADS))
        self.assertTrue(controls.isdisjoint(PRIVATE_LEADS))

    def test_twenty_two_characters_fit_eleven_stock_cells(self) -> None:
        text = "0123456789ABCDEFGHIJKL"
        self.assertEqual(len(text), 22)
        dictionary = PackedEnglishDictionary.from_texts([text])
        encoded = dictionary.encode_visible_text(text)
        self.assertEqual(len(encoded), 22)
        self.assertEqual(len(encoded) // 2, 11)
        self.assertEqual(dictionary.decode_visible_text(encoded), text)

    def test_odd_character_is_padded_inside_final_pair(self) -> None:
        dictionary = PackedEnglishDictionary.from_texts(["HELLO"])
        encoded = dictionary.encode_visible_text("HELLO")
        self.assertEqual(dictionary.decode_visible_text(encoded), "HELLO ")
        self.assertEqual(
            dictionary.decode_visible_text(encoded, strip_pad=True),
            "HELLO",
        )

    def test_pair_table_uses_one_byte_glyph_ids(self) -> None:
        dictionary = PackedEnglishDictionary.from_texts(
            ["Sengoku: “Move.”", "¥500"]
        )
        table = dictionary.runtime_pair_table()
        self.assertEqual(len(table), len(dictionary.pairs) * 2)
        self.assertTrue(all(value < len(DEFAULT_DISPLAY_CHARACTERS) for value in table))

    def test_dictionary_is_deterministic_across_input_order(self) -> None:
        first = PackedEnglishDictionary.from_texts(["BENTEN", "SENGOKU"])
        second = PackedEnglishDictionary.from_texts(["SENGOKU", "BENTEN"])
        self.assertEqual(first.pairs, second.pairs)
        self.assertEqual(first.runtime_pair_table(), second.runtime_pair_table())

    def test_repertoire_supports_final_localization_punctuation(self) -> None:
        repertoire = GlyphRepertoire()
        for character in "“”‘’—–…¥■":
            self.assertIsInstance(repertoire.glyph_id(character), int)

    def test_unknown_glyph_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackedEnglishError, "not present"):
            PackedEnglishDictionary.from_texts(["café"])

    def test_dictionary_capacity_is_enforced(self) -> None:
        repertoire = GlyphRepertoire(" " + "".join(chr(i) for i in range(33, 127)))
        # Synthetic distinct two-character pairs.  The constructor itself is
        # the capacity gate; no source text assumptions are involved here.
        pairs = tuple(
            f"{chr(33 + (index // 94) % 94)}{chr(33 + index % 94)}"
            for index in range(PRIVATE_TOKEN_CAPACITY + 1)
        )
        with self.assertRaisesRegex(PackedEnglishError, "exceed"):
            PackedEnglishDictionary(pairs, repertoire)


if __name__ == "__main__":
    unittest.main()
