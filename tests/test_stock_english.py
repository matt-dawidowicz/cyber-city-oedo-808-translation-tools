from __future__ import annotations

import pathlib
import tempfile
import unittest

from cyber_oedo.build.english_resources_test import load_english_tsv
from cyber_oedo.text import stock_english
from cyber_oedo.text.extract_dialogue import parse_record

GLYPH = b"\x82\xa0"


def source(pages: int) -> bytes:
    return b"\x27\x28" + b"\x40".join([GLYPH] * pages) + b"\x00"


class StockRecordTests(unittest.TestCase):
    def test_page_controls_counts_only_page_breaks(self) -> None:
        self.assertEqual(stock_english.page_controls(source(3)), 2)
        with self.assertRaisesRegex(stock_english.StockEnglishError, "other than page breaks"):
            stock_english.page_controls(b"\x27\x28" + GLYPH + b"\x2f" + GLYPH + b"\x00")

    def test_compile_adds_pages_and_keeps_marker_and_terminator(self) -> None:
        text = "Man: “I don’t know the details, but it sounds like several wanted criminals have gathered.”"
        record = stock_english.compile_stock_record(source(1), text)
        parsed = parse_record(record, 2, limit=len(record) - 2)
        lines = stock_english.wrap_stock_lines(" ".join(text.split()))
        self.assertTrue(record.startswith(b"\x27\x28") and record.endswith(b"\x00"))
        self.assertEqual(parsed.controls, (0x40,) * (-(-len(lines) // 3) - 1))

    def test_english_needing_fewer_pages_than_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(stock_english.StockEnglishError, "must not remove"):
            stock_english.compile_stock_record(source(3), "Short.")


class EnglishTsvTests(unittest.TestCase):
    def write(self, text: str) -> pathlib.Path:
        directory = tempfile.mkdtemp()
        path = pathlib.Path(directory) / "english.tsv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_reads_offsets_and_normalises_spacing(self) -> None:
        path = self.write("payload_offset\tenglish\n0x00175828\t  Hello   there \n0x10\t\n")
        self.assertEqual(load_english_tsv(path), {0x175828: "Hello there"})

    def test_rejects_duplicates_and_missing_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_english_tsv(self.write("payload_offset\tenglish\n0x10\ta\n16\tb\n"))
        with self.assertRaisesRegex(ValueError, "columns"):
            load_english_tsv(self.write("offset\ttext\n0x10\ta\n"))


if __name__ == "__main__":
    unittest.main()
