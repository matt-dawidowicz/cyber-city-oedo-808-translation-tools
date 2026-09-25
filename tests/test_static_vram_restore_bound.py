from __future__ import annotations

import unittest

from cyber_oedo.runtime.static_vram_restore_bound import (
    GLYPH_WORDS_WRITTEN_PER_CELL,
    TEXT_CELLS,
    build_static_vram_restore_bound,
    glyph_dirty_ranges,
)


class StaticVramRestoreBoundTests(unittest.TestCase):
    def test_all_grid_slots_have_sparse_32_word_writes(self) -> None:
        rows = glyph_dirty_ranges()
        self.assertEqual(len(rows), TEXT_CELLS)
        self.assertEqual(GLYPH_WORDS_WRITTEN_PER_CELL, 0x20)
        self.assertTrue(all(end - start == 0x20 for start, end in rows))
        self.assertEqual(rows[0], (0x6D00, 0x6D20))
        self.assertEqual(rows[-1], (0x75C0, 0x75E0))

    def test_portrait_plus_sparse_glyphs_are_small_fraction_of_scene(self) -> None:
        report = build_static_vram_restore_bound()
        known = report["known_without_bat"]
        self.assertEqual(known["sparse_bytes"], 8224 + 36 * 64)
        self.assertLess(known["sparse_percent_of_full_scene"], 18.0)
        self.assertLess(known["envelope_percent_of_full_scene"], 22.0)

    def test_bat_bound_remains_explicitly_unproven(self) -> None:
        report = build_static_vram_restore_bound()
        self.assertIsNone(report["bat"]["exact_union_static_bound"])
        self.assertFalse(report["release_enabled"])


if __name__ == "__main__":
    unittest.main()
