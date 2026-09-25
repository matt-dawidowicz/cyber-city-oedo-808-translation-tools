from __future__ import annotations

import unittest

from cyber_oedo.runtime.vram_dirty_profile import (
    DirtyRange,
    SCENE_RESTORE_BYTES,
    build_vram_dirty_report,
    merge_ranges,
)


class VramDirtyProfileTests(unittest.TestCase):
    def test_merge_ranges_coalesces_overlap_and_requested_gap(self) -> None:
        source = (
            DirtyRange(0x100, 0x10F),
            DirtyRange(0x110, 0x11F),
            DirtyRange(0x124, 0x12F),
        )
        self.assertEqual(merge_ranges(source), (DirtyRange(0x100, 0x11F), DirtyRange(0x124, 0x12F)))
        self.assertEqual(merge_ranges(source, maximum_gap=4), (DirtyRange(0x100, 0x12F),))

    def test_report_matches_profiler_unique_count(self) -> None:
        log = """
[VRAM_DIRTY_SUMMARY 1] frame=100 unique_changed_bytes=24 all_writes=40 changed_writes=30
[VRAM_DIRTY_RANGE 001] byte=$1001-$1008 bytes=8 vdc_word~=$0800-$0804
[VRAM_DIRTY_RANGE 002] byte=$1010-$101F bytes=16 vdc_word~=$0808-$080F
[VRAM_DIRTY_RANGES_TOTAL] 2
"""
        report = build_vram_dirty_report(log, transfer_alignment=2)
        session = report["sessions"][0]
        self.assertEqual(session["aligned_restore_bytes"], 26)
        self.assertEqual(session["stock_scene_restore_bytes"], SCENE_RESTORE_BYTES)
        self.assertEqual(session["bytes_avoided_vs_stock"], SCENE_RESTORE_BYTES - 26)

    def test_alignment_and_merge_gap_trade_copy_calls_for_bytes(self) -> None:
        log = """
[VRAM_DIRTY_SUMMARY 2] frame=200 unique_changed_bytes=16 all_writes=20 changed_writes=16
[VRAM_DIRTY_RANGE 001] byte=$2000-$2007 bytes=8 vdc_word~=$1000-$1003
[VRAM_DIRTY_RANGE 002] byte=$200C-$2013 bytes=8 vdc_word~=$1006-$1009
[VRAM_DIRTY_RANGES_TOTAL] 2
"""
        strict = build_vram_dirty_report(log, merge_gap=0, transfer_alignment=2)["sessions"][0]
        grouped = build_vram_dirty_report(log, merge_gap=4, transfer_alignment=2)["sessions"][0]
        self.assertEqual(strict["aligned_range_count"], 2)
        self.assertEqual(strict["aligned_restore_bytes"], 16)
        self.assertEqual(grouped["aligned_range_count"], 1)
        self.assertEqual(grouped["aligned_restore_bytes"], 20)

    def test_incomplete_session_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncated"):
            build_vram_dirty_report(
                "[VRAM_DIRTY_SUMMARY 1] frame=1 unique_changed_bytes=2 all_writes=2 changed_writes=2\\n"
            )


if __name__ == "__main__":
    unittest.main()
