from __future__ import annotations

import unittest

from cyber_oedo.runtime.fast_load_stack import (
    BAR_CACHE_LAYOUT,
    CARD_RAM_LAST_BANK,
    METADATA_CAPACITY,
    build_bar_fast_load_stack,
)


class FastLoadStackTests(unittest.TestCase):
    def test_bar_layout_fits_super_system_card_ram(self) -> None:
        self.assertLessEqual(max(item.last_bank for item in BAR_CACHE_LAYOUT), CARD_RAM_LAST_BANK)
        report = build_bar_fast_load_stack()
        self.assertEqual(report["card_ram"]["allocated_bank_range"], "$68-$72")
        self.assertEqual(report["card_ram"]["allocated_banks"], 11)
        self.assertEqual(report["card_ram"]["banks_remaining"], 13)

    def test_module_local_bank_has_metadata_slack(self) -> None:
        self.assertEqual(METADATA_CAPACITY, 0xAF)
        report = build_bar_fast_load_stack()
        self.assertEqual(report["metadata"]["bank"], "$6C")
        self.assertEqual(report["metadata"]["capacity_bytes"], 0xAF)

    def test_fail_closed_fallbacks_are_explicit(self) -> None:
        report = build_bar_fast_load_stack()
        self.assertIn("fail closed", report["metadata"]["policy"])
        actions = " ".join(item["action"] for item in report["fill_lifecycle"])
        self.assertIn("fall back", actions)

    def test_only_measured_numbers_are_numeric(self) -> None:
        evidence = build_bar_fast_load_stack()["measured_evidence"]
        self.assertEqual(evidence["entry_frames_saved"], 121)
        self.assertEqual(evidence["selective_cd_frames_saved"], 139)
        self.assertIsInstance(evidence["card_ram_scene_restore"], str)

    def test_stack_remains_release_disabled(self) -> None:
        self.assertFalse(build_bar_fast_load_stack()["release_enabled"])


if __name__ == "__main__":
    unittest.main()
