"""Seamless VWF cell layout and optional source-authenticated Mission 0 pilot."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from cyber_oedo.runtime.mission0_pool_pilot import (
    VWF_SECTOR_RELATIVE, VWF_BANK_BYTES, _make_runtime,
    build_m0b_pilot_disc, build_m0b_pilot_patches,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.oedo_pixel_font import authored_atlas, authored_vwf
from cyber_oedo.text.vwf_exact_cells import compile_exact_vwf
from cyber_oedo.text.vwf_cells import (
    VwfCellCompileError, compile_vwf_text,
    decode_vwf_token, render_vwf_dictionary,
)
from cyber_oedo.text.vwf_text import LINE_PIXELS, render_line
from tests.test_mission0_pool_pilot import SourceCodeView


class ExactVwfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.font = authored_vwf()

    def test_reconstruct_entire_line_exactly_from_each_native_16px_cell(self):
        for line in (
            "Bartender: Welcome.",
            "“You’re late,” Sengoku.",
            "iiiiWWWWllll MMMM ...",
            "¥500—No kidding!",
            "Benten: I see.",
        ):
            layout = compile_exact_vwf(line, self.font)
            expected = render_line(line, self.font)
            self.assertEqual(layout.cell_count, (expected.pixel_width + 15) // 16)
            self.assertEqual(layout.stream[:2], bytes.fromhex("7D 56"))
            self.assertEqual(layout.stream[-3:], bytes.fromhex("FF FF 00"))
            pixels = [0] * 16
            for index in range(layout.cell_count):
                start = 2 + index * 2
                token = decode_vwf_token(layout.stream[start:start + 2])
                bitmap = layout.staged_cells[token * 32:(token + 1) * 32]
                self.assertEqual(len(bitmap), 32)
                for row in range(16):
                    pixels[row] |= int.from_bytes(
                        bitmap[row * 2:row * 2 + 2], "big"
                    ) << (LINE_PIXELS - (index + 1) * 16)
            self.assertEqual(tuple(pixels), expected.bitmap_rows, line)

    def test_greedy_glyph_packing_left_slack_exact_layout_removes(self):
        line = "Bartender: Welcome."
        glyphs = EnglishGlyphTable.from_texts((line, " ?"))
        font = authored_vwf(glyphs.characters)
        exact = compile_exact_vwf(line, font)
        old = compile_vwf_text(line, font, glyphs)
        self.assertNotEqual(
            exact.staged_cells, render_vwf_dictionary(old.dictionary, font)
        )

    def test_source_controls_for_two_lines_and_bounded_three_row_view(self):
        result = compile_exact_vwf(("“I never said that.” " * 3).strip(), self.font)
        self.assertEqual(len(result.line_texts), 2)
        self.assertIn(bytes.fromhex("FF FF 40 7D 56"), result.stream)
        with self.assertRaisesRegex(VwfCellCompileError, "three lines"):
            compile_exact_vwf(("Hello. " * 60).strip(), self.font)

    def test_pilot_source_guard_dictionary_disc_and_no_default_change(self):
        english = "Bartender: Welcome."
        glyphs = EnglishGlyphTable.from_texts((english, " ?"))
        atlas = authored_atlas(glyphs.characters)
        runtime = _make_runtime(glyphs, atlas, vwf_loader=True)
        sparse = SourceCodeView(len(runtime.font), len(runtime.full_code))
        sparse.slices[(VWF_SECTOR_RELATIVE * 2048, VWF_BANK_BYTES)] = bytes(
            VWF_BANK_BYTES
        )
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            edits = build_m0b_pilot_patches(
                sparse, glyphs, atlas, english=english, vwf_pilot=True
            )
        self.assertEqual(len(edits), 11)
        pool = next(item for item in edits if "four Card RAM banks" in item.label)
        self.assertEqual(pool.replacement[:2], bytes.fromhex("7D 56"))
        vwf = next(item for item in edits if "VWF exact" in item.label)
        self.assertEqual(vwf.offset, VWF_SECTOR_RELATIVE * 2048)
        self.assertNotEqual(vwf.replacement[:32], bytes(32))
        self.assertTrue(all(
            item.expected == sparse[item.offset:item.end_offset]
            for item in edits
        ))
        sparse.slices[(VWF_SECTOR_RELATIVE * 2048, VWF_BANK_BYTES)] = bytes(
            (1,)
        ) + bytes(VWF_BANK_BYTES - 1)
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            with self.assertRaisesRegex(ValueError, "signature mismatch"):
                build_m0b_pilot_patches(
                    sparse, glyphs, atlas, english=english, vwf_pilot=True
                )

    def test_native_pool_audits_each_vwf_line_not_one_total(self) -> None:
        from cyber_oedo.runtime.external_english_pool import (
            inspect_native_pool_record,
        )

        cases = (
            ("Bartender: Welcome.", 1),
            ("Bartender: Welcome. Do you know the Old City?", 2),
            (
                "Bartender: Welcome. You look like trouble. "
                "This bar is no place to make enemies.",
                3,
            ),
        )
        for english, expected in cases:
            with self.subTest(line_count=expected):
                glyphs = EnglishGlyphTable.from_texts((english, " ?"))
                atlas = authored_atlas(glyphs.characters)
                runtime = _make_runtime(glyphs, atlas, vwf_loader=True)
                sparse = SourceCodeView(len(runtime.font), len(runtime.full_code))
                sparse.slices[(VWF_SECTOR_RELATIVE * 2048, VWF_BANK_BYTES)] = bytes(
                    VWF_BANK_BYTES
                )
                with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
                    edits = build_m0b_pilot_patches(
                        sparse, glyphs, atlas, english=english, vwf_pilot=True
                    )
                pool = next(x for x in edits if "four Card RAM banks" in x.label)
                audit = inspect_native_pool_record(pool.replacement, 0)
                self.assertEqual(audit.vwf_segments, expected)
                self.assertEqual(audit.fixed_segments, 0)

    def test_vwf_opt_in_requires_authored_pixel_source(self):
        with self.assertRaisesRegex(ValueError, "requires"):
            build_m0b_pilot_disc(
                Path("unavailable_original.ccd"), Path("do-not-create"),
                None, vwf_pilot=True
            )


if __name__ == "__main__":
    unittest.main()
