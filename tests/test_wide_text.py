"""Test the host-side wide-English renderer format prototype."""

from __future__ import annotations

import unittest

from wide_text import (
    WIDE_END,
    WIDE_NEWLINE,
    WIDE_START,
    WideTextError,
    WideTextPrototype,
    wrap_wide_english,
)


class WideTextTests(unittest.TestCase):
    """Keep the proposed 22-column escape format explicit and reviewable."""

    def test_wraps_at_word_boundaries(self) -> None:
        """Use a second line only when a complete word would overflow."""

        self.assertEqual(
            wrap_wide_english("THE CITY NEVER SLEEPS TONIGHT"),
            ("THE CITY NEVER SLEEPS", "TONIGHT"),
        )

    def test_encodes_printable_bytes_between_escape_markers(self) -> None:
        """Keep the proposed stream self-delimiting for a parser hook."""

        stream = WideTextPrototype("LOOK AT THE REGISTRY").encoded
        self.assertEqual(stream[0], WIDE_START)
        self.assertEqual(stream[-1], WIDE_END)
        self.assertNotIn(WIDE_NEWLINE, stream[1:-1])
        self.assertEqual(stream[1:-1], b"LOOK AT THE REGISTRY")

    def test_multiline_encoding_preserves_wrapped_words(self) -> None:
        """Place line separators only between complete wrapped ASCII lines."""

        prototype = WideTextPrototype("THE CITY NEVER SLEEPS TONIGHT")
        self.assertEqual(prototype.lines, ("THE CITY NEVER SLEEPS", "TONIGHT"))
        self.assertEqual(
            prototype.encoded,
            bytes((WIDE_START,))
            + b"THE CITY NEVER SLEEPS"
            + bytes((WIDE_NEWLINE,))
            + b"TONIGHT"
            + bytes((WIDE_END,)),
        )
        self.assertEqual(
            b" ".join(prototype.encoded[1:-1].split(bytes((WIDE_NEWLINE,)))),
            prototype.english.encode("ascii"),
        )

    def test_exact_width_and_boolean_width_are_unambiguous(self) -> None:
        """Accept exact-fit words but reject bool's accidental int subclass."""

        self.assertEqual(wrap_wide_english("ABCD", width=4), ("ABCD",))
        with self.assertRaisesRegex(WideTextError, "positive integer"):
            wrap_wide_english("A", width=True)

    def test_rejects_invalid_text_spacing_and_width_inputs(self) -> None:
        """Reject host inputs that would make the byte stream ambiguous."""

        invalid_inputs = (
            (None, 22, "non-empty"),
            ("", 22, "non-empty"),
            (" LEADING", 22, "single interior"),
            ("TRAILING ", 22, "single interior"),
            ("DOUBLE  SPACE", 22, "single interior"),
            ("DEL\x7f", 22, "printable ASCII"),
            ("A", 0, "positive integer"),
            ("A", 22.0, "positive integer"),
        )
        for text, width, message in invalid_inputs:
            with self.subTest(text=text, width=width):
                with self.assertRaisesRegex(WideTextError, message):
                    wrap_wide_english(text, width=width)

    def test_rejects_unrepresentable_or_overwide_wording(self) -> None:
        """Fail before unsupported text can reach a future game build."""

        with self.assertRaisesRegex(WideTextError, "printable ASCII"):
            wrap_wide_english("CAFÉ")
        with self.assertRaisesRegex(WideTextError, "exceeds"):
            wrap_wide_english(
                "PNEUMONOULTRAMICROSCOPICSILICOVOLCANOCONIOSIS"
            )


if __name__ == "__main__":
    unittest.main()
