from __future__ import annotations

import unittest

from cyber_oedo.build.profiles.ui_english import (
    COMMON_COMMAND_LABELS,
    MODE_LABELS,
    OPENING_MENU_AND_READOUTS,
)


class EnglishUiProfileTests(unittest.TestCase):
    def test_common_command_table_has_all_37_entries(self) -> None:
        self.assertEqual(len(COMMON_COMMAND_LABELS), 37)
        self.assertEqual(COMMON_COMMAND_LABELS[0].english, "Look")
        self.assertEqual(COMMON_COMMAND_LABELS[18].english, "Travel")
        self.assertEqual(COMMON_COMMAND_LABELS[-1].english, "Mode")

    def test_move_and_travel_remain_distinct(self) -> None:
        translations = {
            item.source: item.english
            for item in COMMON_COMMAND_LABELS
        }
        self.assertEqual(translations["動かす"], "Move")
        self.assertEqual(translations["移動"], "Travel")

    def test_mode_terminology_is_consistent(self) -> None:
        translations = {item.source: item.english for item in MODE_LABELS}
        self.assertEqual(translations["捜査モード"], "Investigation Mode")
        self.assertEqual(translations["推理モード"], "Deduction Mode")
        self.assertEqual(translations["迎撃モード"], "Intercept Mode")

    def test_opening_offsets_are_unique_and_ordered(self) -> None:
        offsets = [item.payload_offset for item in OPENING_MENU_AND_READOUTS]
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertEqual(offsets, sorted(offsets))

    def test_terminal_readouts_use_consistent_register(self) -> None:
        terminal = [
            item.english
            for item in OPENING_MENU_AND_READOUTS
            if item.presentation.startswith("terminal")
        ]
        self.assertIn("CD-ROM DRIVE........READY", terminal)
        self.assertIn("ADPCM DRIVER........INSTALLED", terminal)
        self.assertIn("** O-E-D-O MAIN DATABASE **", terminal)


if __name__ == "__main__":
    unittest.main()
