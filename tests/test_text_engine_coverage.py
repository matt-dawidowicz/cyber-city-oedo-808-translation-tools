from __future__ import annotations

import unittest

from cyber_oedo.runtime.text_engine_coverage import (
    COMMON_UI_OVERLAY_BASES,
    COMMON_UI_TABLE,
    DYNAMIC_LABEL_SOURCE,
    ENDING_COMPLETION_STREAM,
    ENDING_PRESENTATION_PARSER,
    RESOURCE_TEXT_FAMILIES,
    decode_dynamic_label_records,
    decode_ending_completion_stream,
    decode_fixed_ui_table,
)


class TextEngineCoverageTests(unittest.TestCase):
    def test_fixed_ui_table_decodes_shift_jis_and_preserves_metadata(self) -> None:
        first = "見る".encode("shift_jis") + b"\x00"
        second = "移動".encode("shift_jis") + b"\x00"
        blob = (
            first.ljust(16, b"\xAA")
            + second.ljust(16, b"\xBB")
        )
        rows = decode_fixed_ui_table(blob)
        self.assertEqual(rows[0]["label"], "見る")
        self.assertEqual(rows[1]["label"], "移動")
        self.assertTrue(rows[0]["metadata_hex"].endswith("aa"))

    def test_dynamic_label_table_has_two_text_slots_per_record(self) -> None:
        blob = bytearray(769)
        first = bytearray(32)
        first[:5] = "見る".encode("shift_jis") + b"\x00"
        alternate = "話す".encode("shift_jis") + b"\x00"
        first[13 : 13 + len(alternate)] = alternate
        first[26] = 0x7F
        blob[:32] = first

        rows = decode_dynamic_label_records(bytes(blob))
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0]["primary"], "見る")
        self.assertEqual(rows[0]["alternate"], "話す")
        self.assertTrue(rows[0]["state_hex"].startswith("7f"))

    def test_ending_stream_decodes_shift_jis_and_ascii_opcodes(self) -> None:
        blob = (
            bytes((0, 6, 2))
            + "ＭＩＳＳＩＯＮ".encode("shift_jis")
            + b"\x00"
            + bytes((1, 10, 7))
            + "セーブ".encode("shift_jis")
            + b"\x00"
            + bytes((2, 0, 25))
            + b"@1991 NCS CORP."
            + b"\x00\xFF"
        )
        rows = decode_ending_completion_stream(blob)
        self.assertEqual([row["opcode"] for row in rows], [0, 1, 2])
        self.assertEqual(rows[0]["encoding"], "shift_jis")
        self.assertEqual(rows[2]["encoding"], "ascii")
        self.assertEqual(rows[2]["text"], "@1991 NCS CORP.")

    def test_ending_stream_rejects_unknown_opcode(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported ENDING text opcode"):
            decode_ending_completion_stream(b"\x03\x00\x00\x00\xFF")

    def test_gamewide_family_constants_remain_explicit(self) -> None:
        self.assertEqual(DYNAMIC_LABEL_SOURCE.length, 769)
        self.assertEqual(COMMON_UI_TABLE.length, 0x250)
        self.assertEqual(ENDING_COMPLETION_STREAM.length, 0x185)
        self.assertEqual(ENDING_PRESENTATION_PARSER.length, 0x2F5)
        self.assertEqual(len(COMMON_UI_OVERLAY_BASES), 9)
        self.assertIn("INVENTRY", RESOURCE_TEXT_FAMILIES)
        self.assertIn("DEN_EREV", RESOURCE_TEXT_FAMILIES)
        self.assertIn("KIDOU", RESOURCE_TEXT_FAMILIES)


if __name__ == "__main__":
    unittest.main()
