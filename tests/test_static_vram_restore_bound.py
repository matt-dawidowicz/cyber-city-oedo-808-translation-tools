from __future__ import annotations

import unittest

from cyber_oedo.runtime.static_vram_restore_bound import (
    GLYPH_WORDS_WRITTEN_PER_CELL,
    TEXT_CELLS,
    build_static_vram_restore_bound,
    glyph_dirty_ranges,
    LIVE_BAR_SELECTIVE_RESTORE_FRAMES,
    LIVE_BAR_STOCK_RESTORE_FRAMES,
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

    def test_live_bar_two_span_candidate_matches_measured_benchmark(self) -> None:
        live = build_static_vram_restore_bound()["live_bar_capture"]
        candidate = live["selective_two_span_candidate"]
        self.assertEqual(live["total_dirty_bytes"], 33163)
        self.assertEqual(live["dirty_inside_stock_restore_region_bytes"], 32225)
        self.assertEqual(candidate["transfer_bytes"], 0x8E20 + 0x1A00)
        self.assertEqual(candidate["bytes_skipped_vs_stock"], 17888)
        self.assertEqual(LIVE_BAR_STOCK_RESTORE_FRAMES, 551)
        self.assertEqual(LIVE_BAR_SELECTIVE_RESTORE_FRAMES, 412)
        self.assertEqual(candidate["frames_saved"], 139)
        self.assertTrue(candidate["post_restore_vram_matches_stock"])
        self.assertTrue(candidate["visual_bar_return_verified"])
        self.assertFalse(candidate["release_safe"])


if __name__ == "__main__":
    unittest.main()
