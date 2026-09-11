"""Tests for the build-time English typography contract."""

from __future__ import annotations

import unittest

from cyber_oedo.text.typography import (
    CORPUS_TYPOGRAPHY_EXTENSIONS,
    PRINTABLE_ASCII,
    PRODUCTION_REPERTOIRE,
    FontMetrics,
    GlyphMetric,
    PixelGeometry,
    packed_font_bytes,
    wrap_text_pixels,
)


class TypographyContractTests(unittest.TestCase):
    """Keep repertoire, storage budgets, and pixel wrapping deterministic."""

    def test_production_repertoire_covers_current_corpus_extensions(self) -> None:
        self.assertEqual(95, len(PRINTABLE_ASCII))
        self.assertEqual(8, len(CORPUS_TYPOGRAPHY_EXTENSIONS))
        self.assertEqual(103, len(PRODUCTION_REPERTOIRE))
        self.assertEqual(
            len(PRODUCTION_REPERTOIRE), len(set(PRODUCTION_REPERTOIRE))
        )
        alphanumeric = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789"
        )
        for character in alphanumeric:
            self.assertIn(character, PRODUCTION_REPERTOIRE)
        for character in "¥–—‘’“”■":
            self.assertIn(character, PRODUCTION_REPERTOIRE)

    def test_three_one_bit_fonts_are_under_five_kibibytes(self) -> None:
        per_font = packed_font_bytes(len(PRODUCTION_REPERTOIRE))
        self.assertEqual(1648, per_font)
        self.assertEqual(4944, per_font * 3)

    def test_proportional_measurement_and_wrapping(self) -> None:
        metrics = FontMetrics(
            name="test",
            role="dialogue",
            glyphs=(
                GlyphMetric(" ", 2),
                GlyphMetric("I", 3),
                GlyphMetric("M", 8),
                GlyphMetric("a", 5),
            ),
        )
        geometry = PixelGeometry(width_pixels=18, maximum_lines=2)
        self.assertEqual(18, metrics.measure("I Ma"))
        self.assertEqual(
            ("I Ma", "Ma"), wrap_text_pixels("I Ma Ma", metrics, geometry)
        )

    def test_unknown_glyph_is_rejected(self) -> None:
        metrics = FontMetrics.fixed_width("ascii", "dialogue", " ab")
        with self.assertRaisesRegex(ValueError, "does not contain"):
            metrics.measure("abc")

    def test_word_that_cannot_fit_is_rejected(self) -> None:
        metrics = FontMetrics.fixed_width("tiny", "dialogue", " abc")
        with self.assertRaisesRegex(ValueError, "word exceeds"):
            wrap_text_pixels("abc", metrics, PixelGeometry(16, 2))


if __name__ == "__main__":
    unittest.main()
