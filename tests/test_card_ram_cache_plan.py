from __future__ import annotations

import unittest

from cyber_oedo.runtime.card_ram_cache_plan import (
    BAR_ADPCM_INCREMENTAL_SAVED_FRAMES,
    BAR_COMBINED_CACHE_SAVED_FRAMES,
    BAR_PORTRAIT_CACHE_SAVED_FRAMES,
    CARD_RAM_BANK_BYTES,
    build_ad_write_safe_core_layout,
    build_cache_plan,
)


class CardRamCachePlanTests(unittest.TestCase):
    def test_core_layout_never_crosses_a_bank(self) -> None:
        rows = build_ad_write_safe_core_layout()
        self.assertEqual(len({item.bank for item in rows}), 12)
        self.assertTrue(
            all(item.end_offset_exclusive <= CARD_RAM_BANK_BYTES for item in rows)
        )

    def test_all_active_adpcm_blocks_are_dedicated_banks(self) -> None:
        rows = build_ad_write_safe_core_layout()
        audio = [item for item in rows if item.name.startswith("speaker_adpcm_")]
        self.assertEqual(len(audio), 7)
        self.assertTrue(all(item.offset == 0 for item in audio))
        self.assertTrue(all(item.byte_length == CARD_RAM_BANK_BYTES for item in audio))

    def test_module_and_one_local_fit_in_one_bank(self) -> None:
        rows = build_ad_write_safe_core_layout()
        module = next(item for item in rows if item.name == "dialogue_module")
        local0 = next(item for item in rows if item.name == "speaker_local_0")
        self.assertEqual(module.bank, local0.bank)
        self.assertEqual(local0.offset, module.end_offset_exclusive)
        self.assertLessEqual(local0.end_offset_exclusive, CARD_RAM_BANK_BYTES)

    def test_capacity_lower_bound_is_not_execution_layout(self) -> None:
        report = build_cache_plan()
        self.assertEqual(report["capacity_lower_bound"]["banks"], 14)
        self.assertEqual(report["ad_write_safe_core"]["banks"], 12)
        self.assertEqual(
            report["two_portrait_extensions"]["segmented_copy"]["total_banks"], 15
        )
        self.assertEqual(
            report["two_portrait_extensions"]["independent_two_bank_portraits"]["total_banks"],
            16,
        )

    def test_live_bartender_cache_benchmark_matches_measured_frames(self) -> None:
        report = build_cache_plan()["live_bartender_cache_benchmark"]
        self.assertEqual(BAR_PORTRAIT_CACHE_SAVED_FRAMES, 95)
        self.assertEqual(BAR_ADPCM_INCREMENTAL_SAVED_FRAMES, 26)
        self.assertEqual(BAR_COMBINED_CACHE_SAVED_FRAMES, 121)
        self.assertEqual(report["stock"]["input_to_parser_frames"], 457)
        self.assertEqual(report["portrait_cache"]["input_to_parser_frames"], 362)
        combined = report["portrait_plus_adpcm_cache"]
        self.assertEqual(combined["input_to_parser_frames"], 336)
        self.assertTrue(combined["full_vram_matches_stock"])
        self.assertTrue(combined["full_adpcm_matches_stock"])

    def test_plan_remains_release_disabled(self) -> None:
        self.assertFalse(build_cache_plan()["release_enabled"])


if __name__ == "__main__":
    unittest.main()
