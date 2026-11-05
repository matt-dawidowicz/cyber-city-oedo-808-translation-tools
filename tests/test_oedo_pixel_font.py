"""Tests for source-authored Oedo pixels and native English coverage gates."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cyber_oedo.runtime.mission0_pool_pilot import _make_runtime
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.oedo_pixel_font import (
    BASELINE,
    DESCEND_BOTTOM,
    NATIVE_GLYPH_LIMIT,
    PILOT_CHARACTERS,
    OedoPixelFontError,
    audit_glyphs,
    audit_translation_file,
    authored_atlas,
    authored_vwf,
    glyph_bitmap,
)
from cyber_oedo.text.packed_english import DEFAULT_DISPLAY_CHARACTERS
from cyber_oedo.text.vwf_text import measure_text, render_line, wrap_vwf


class OedoPixelTests(unittest.TestCase):
    def test_curated_95_slots_not_a_fictitious_400_symbol_font(self) -> None:
        self.assertEqual(len(PILOT_CHARACTERS), NATIVE_GLYPH_LIMIT)
        self.assertEqual(len(set(PILOT_CHARACTERS)), 95)
        self.assertFalse(set("“”‘’—–…¥■") - set(PILOT_CHARACTERS))
        self.assertFalse(any(char in PILOT_CHARACTERS for char in "éñü½÷π"))

    def test_every_documented_ascii_or_special_symbol_can_be_authored(self) -> None:
        self.assertEqual(len(DEFAULT_DISPLAY_CHARACTERS), 104)
        for char in DEFAULT_DISPLAY_CHARACTERS:
            glyph = glyph_bitmap(char)
            self.assertEqual(len(glyph), 16)
            self.assertEqual(glyph[:3] + glyph[14:], bytes(5))
            self.assertEqual(any(glyph), char != " ", char)

    def test_all_letters_share_baseline_and_descenders_are_lower(self) -> None:
        for char in "HMWABceno1":
            rows = glyph_bitmap(char)
            self.assertLessEqual(max(i for i, bits in enumerate(rows) if bits), BASELINE)
        for char in "gjpqy,":
            glyph = glyph_bitmap(char)
            self.assertTrue(any(glyph[BASELINE + 1:DESCEND_BOTTOM + 1]), char)
        self.assertFalse(any(glyph_bitmap(".")[BASELINE + 1:]))

    def test_proportional_widths_and_pixel_wrap(self) -> None:
        font = authored_vwf()
        self.assertEqual(font.metric(" ").advance, 4)
        self.assertGreater(font.metric("W").advance, font.metric("l").advance)
        self.assertGreater(font.metric("M").advance, font.metric("i").advance)
        self.assertGreater(measure_text("WWW", font), measure_text("iii", font))
        lines = wrap_vwf(
            "“You’re late,” Sengoku. — ¥500!",
            font, max_pixels=95
        )
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(render_line(line, font).pixel_width <= 95 for line in lines))

    def test_atlas_fits_both_source_and_native_runtime_layout(self) -> None:
        atlas = authored_atlas()
        self.assertEqual(len(atlas.binary()), 95 * 16)
        self.assertEqual(atlas.source_sha256, authored_atlas().source_sha256)
        runtime = _make_runtime(EnglishGlyphTable(PILOT_CHARACTERS), atlas)
        self.assertLess(0xB000 + len(runtime.full_code), 0xC000)

    def test_strict_missing_glyph_with_unicode_name_and_occurrence_count(self) -> None:
        audit = audit_glyphs(["Sengoku: Welcome.", "Café", "Café!"])
        self.assertEqual(audit.missing[0]["character"], "é")
        self.assertEqual(audit.missing[0]["codepoint"], "U+00E9")
        self.assertEqual(audit.missing[0]["occurrences"], 2)
        self.assertFalse(audit.would_fit_native)
        self.assertTrue(audit_glyphs(["“Where’s Benten?” — ¥500… ■"]).would_fit_native)

    def test_native_compiler_reports_exact_missing_glyphs_and_counts(self) -> None:
        from cyber_oedo.text.english_dialogue_engine import (
            EnglishDialogueCompileError,
        )

        with self.assertRaises(EnglishDialogueCompileError) as caught:
            EnglishGlyphTable.from_texts(["Café", "Café!"])
        message = str(caught.exception)
        self.assertIn("U+00E9", message)
        self.assertIn("2 occurrences", message)
        self.assertIn("LATIN SMALL LETTER E WITH ACUTE", message)

    def test_empty_or_over_capacity_unsupported_fails_closed(self) -> None:
        self.assertFalse(audit_glyphs([]).would_fit_native)
        with self.assertRaisesRegex(OedoPixelFontError, "95-slot"):
            authored_atlas(DEFAULT_DISPLAY_CHARACTERS)
        with self.assertRaisesRegex(OedoPixelFontError, "space and question"):
            authored_atlas("ABC")
        with self.assertRaisesRegex(OedoPixelFontError, "U\+00E9"):
            glyph_bitmap("é")

    def test_tsv_audits_only_explicit_visible_translation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "translation.tsv"
            with file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["Japanese Source", "Definitive Localization"])
                writer.writerow(["日本語", "“Hello,” said Benten."])
                writer.writerow(["日本語", "MISSION 01: ¥500"])
            result = audit_translation_file(file)
            self.assertEqual(result.source_rows, 2)
            self.assertEqual(result.missing, ())
            self.assertTrue(result.would_fit_native)

    def test_ambiguous_columns_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "translation.csv"
            file.write_text(
                "English Translation,Definitive Localization\nHello,Howdy\n",
                encoding="utf-8"
            )
            with self.assertRaisesRegex(OedoPixelFontError, "ambiguous"):
                audit_translation_file(file)
            self.assertEqual(
                audit_translation_file(
                    file, column="Definitive Localization"
                ).source_rows, 1
            )


if __name__ == "__main__":
    unittest.main()
