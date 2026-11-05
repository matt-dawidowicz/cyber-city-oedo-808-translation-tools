from __future__ import annotations

import unittest

from cyber_oedo.runtime.opening_menu import (
    DEFAULT_MENU_AUDIO_TRACK,
    MENU_CAVE_CPU,
    MENU_CAVE_OFFSET,
    MENU_STREAM_OFFSET,
    STOCK_MENU_HANDLERS,
    build_definitive_menu_stream,
    build_opening_menu_layout,
)


class OpeningMenuTests(unittest.TestCase):
    def test_stream_ends_before_reclaimed_cave(self) -> None:
        stream = build_definitive_menu_stream()
        self.assertEqual(stream[-1], 0xFF)
        self.assertLess(len(stream), MENU_CAVE_OFFSET - MENU_STREAM_OFFSET)
        self.assertIn(b"OEDO CYBER POLICE", stream)
        self.assertIn(b"SECURE ACCESS TERMINAL", stream)

    def test_stock_selectable_rows_are_preserved(self) -> None:
        stream = build_definitive_menu_stream()
        for y in (10, 14, 18):
            self.assertIn(bytes((0, 8, y)), stream)

    def test_runtime_uses_default_track_and_reclaimed_tail(self) -> None:
        layout = build_opening_menu_layout()
        self.assertEqual(layout.audio_track, DEFAULT_MENU_AUDIO_TRACK)
        self.assertEqual(layout.menu_entry_cpu, MENU_CAVE_CPU)
        self.assertEqual(len(layout.stop_wrapper_cpus), 3)
        self.assertTrue(all(cpu > layout.menu_entry_cpu for cpu in layout.stop_wrapper_cpus))

    def test_wrappers_return_to_original_menu_handlers(self) -> None:
        layout = build_opening_menu_layout()
        for handler in STOCK_MENU_HANDLERS:
            needle = bytes((0x4C, handler & 0xFF, handler >> 8))
            self.assertIn(needle, layout.cave)


if __name__ == "__main__":
    unittest.main()
