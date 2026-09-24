from __future__ import annotations

import unittest

from cyber_oedo.runtime.presentation_stream import (
    KNOWN_FORMATTING_RECORDS,
    decode_presentation_stream,
    unknown_binary_records,
)


class PresentationStreamTests(unittest.TestCase):
    def test_decodes_text_coordinates_and_known_formatting(self) -> None:
        blob = (
            bytes.fromhex("02 01 05 01 06")
            + b"\x00\x00"
            + bytes((1, 3))
            + "ＯＥＤＯＮＥＴ".encode("shift_jis")
            + b"\x00"
            + bytes.fromhex("08 01 20")
            + b"\x00"
            + bytes((2, 6))
            + "見出し".encode("shift_jis")
            + b"\x00"
            + bytes.fromhex("08 09 03")
            + b"\x00"
        )
        rows = decode_presentation_stream(blob)
        self.assertEqual(rows[0].formatting_role, "screen_preamble")
        self.assertEqual(rows[1].kind, "text")
        self.assertEqual((rows[1].x, rows[1].row), (1, 3))
        self.assertEqual(rows[1].text, "ＯＥＤＯＮＥＴ")
        self.assertEqual(rows[2].formatting_role, "heading_layout")
        self.assertEqual(rows[-1].formatting_role, "stream_end")
        self.assertEqual(unknown_binary_records(rows), ())

    def test_unknown_binary_record_is_not_promoted_to_text(self) -> None:
        rows = decode_presentation_stream(bytes.fromhex("AA 01 02 03 00"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, "unknown_binary")

    def test_known_formatting_vocabulary_is_finite(self) -> None:
        self.assertEqual(
            set(KNOWN_FORMATTING_RECORDS.values()),
            {
                "screen_preamble",
                "screen_preamble_tail",
                "heading_layout",
                "body_layout",
                "sidebar_layout_a",
                "sidebar_layout_b",
                "sidebar_or_footer_boundary",
                "stream_end",
                "next_information_page",
                "next_media_mix_page",
            },
        )


if __name__ == "__main__":
    unittest.main()
