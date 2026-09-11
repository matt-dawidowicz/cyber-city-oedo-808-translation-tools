"""Tests for the read-only B3 HuC6280 RAM-bank probe model."""

from __future__ import annotations

import unittest

from cyber_oedo.runtime.ram_probe import (
    B3_RAM_CANDIDATES,
    CD_RAM_BANKS,
    SYSTEM_CARD_3_RAM_BANKS,
    MprSnapshot,
    candidate_mappings,
    summarize_candidate_usage,
)


class RamProbeTests(unittest.TestCase):
    """Keep hardware-bank classification conservative and deterministic."""

    def test_candidate_sets_match_cd_and_system_card_ram(self) -> None:
        self.assertEqual(frozenset(range(0x80, 0x88)), CD_RAM_BANKS)
        self.assertEqual(frozenset(range(0x68, 0x80)), SYSTEM_CARD_3_RAM_BANKS)
        self.assertEqual(
            frozenset(range(0x85, 0x88)) | SYSTEM_CARD_3_RAM_BANKS,
            B3_RAM_CANDIDATES,
        )

    def test_live_bartender_snapshot_maps_no_candidate_bank(self) -> None:
        snapshot = MprSnapshot(
            label="H_BARTEN parser $9543",
            pc=0x9543,
            mprs=(0xFF, 0xF8, 0x80, 0x81, 0x82, 0x83, 0x84, 0x00),
        )
        self.assertEqual((), candidate_mappings(snapshot))

    def test_candidate_mapping_reports_logical_window(self) -> None:
        snapshot = MprSnapshot(
            label="synthetic candidate",
            pc=0x6F50,
            mprs=(0xFF, 0xF8, 0x80, 0x81, 0x82, 0x85, 0x84, 0x00),
        )
        mappings = candidate_mappings(snapshot)
        self.assertEqual(1, len(mappings))
        self.assertEqual(5, mappings[0].mpr)
        self.assertEqual(0x85, mappings[0].physical_bank)
        self.assertEqual(0xA000, mappings[0].logical_start)
        self.assertEqual(0xBFFF, mappings[0].logical_end)

    def test_summary_never_promotes_unsampled_bank_to_free(self) -> None:
        snapshot = MprSnapshot(
            label="H_BARTEN parser $9543",
            pc=0x9543,
            mprs=(0xFF, 0xF8, 0x80, 0x81, 0x82, 0x83, 0x84, 0x00),
        )
        summary = summarize_candidate_usage((snapshot,))
        self.assertIn("no candidate is promoted", summary["ownership_conclusion"])
        self.assertTrue(
            all(
                item["sample_status"] == "not_mapped_in_sample"
                for item in summary["banks"]
            )
        )

    def test_snapshot_requires_exactly_eight_mprs(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly eight"):
            MprSnapshot(label="bad", pc=0, mprs=(0xFF,))


if __name__ == "__main__":
    unittest.main()
