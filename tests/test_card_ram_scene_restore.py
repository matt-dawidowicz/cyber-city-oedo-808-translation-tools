from __future__ import annotations

import unittest

from cyber_oedo.runtime.card_ram_scene_restore import (
    build_restore_routines,
    build_scene_chunks,
    build_snapshot_plan,
)


class CardRamSceneRestoreTests(unittest.TestCase):
    def test_scene_spans_pack_into_six_banks(self) -> None:
        chunks = build_scene_chunks()
        self.assertEqual(len(chunks), 6)
        self.assertEqual([item.bank for item in chunks], list(range(0x6D, 0x73)))
        self.assertEqual(sum(item.byte_length for item in chunks), 0x8E20 + 0x1A00)

    def test_chunk_boundaries_match_live_diff_spans(self) -> None:
        chunks = build_scene_chunks()
        self.assertEqual(chunks[0].vram_byte_start, 0x1200)
        self.assertEqual(chunks[4].vram_byte_start + chunks[4].byte_length, 0xA020)
        self.assertEqual(chunks[5].vram_byte_start, 0xDA00)
        self.assertEqual(chunks[5].vram_byte_start + chunks[5].byte_length, 0xF400)

    def test_restore_machine_code_uses_tia_and_restores_mprs(self) -> None:
        rows = build_restore_routines()
        for row in rows:
            code = row["machine_code"]
            self.assertIn(0xE3, code)  # TIA
            self.assertTrue(code.endswith(bytes.fromhex("68 53 20 68 53 01 60")))
            self.assertTrue(row["direction_live_proven"])

    def test_snapshot_direction_remains_gated(self) -> None:
        plan = build_snapshot_plan()
        self.assertFalse(plan["release_enabled"])
        self.assertTrue(plan["required_validation"])


if __name__ == "__main__":
    unittest.main()
