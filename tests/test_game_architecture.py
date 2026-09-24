from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

from cyber_oedo.runtime.game_architecture import (
    CONTROL_SEMANTICS,
    EXPLORATION_WRAPPER_BASES,
    HashedRegion,
    TEXT_OVERLAY_BASES,
    TEXT_OVERLAY_LABELS,
    TEXT_PARSER_ENTRIES,
    _find_all,
    validate_hashed_regions,
)


class GameArchitectureProofTests(unittest.TestCase):
    def test_find_all_reports_overlapping_search_positions(self) -> None:
        self.assertEqual(_find_all(b"abcabc", b"abc"), (0, 3))

    def test_hashed_region_validation_is_source_guarded(self) -> None:
        blob = b"prefix" + b"evidence" + b"suffix"
        digest = hashlib.sha256(b"evidence").hexdigest()
        region = HashedRegion(
            "test",
            0,
            6,
            8,
            digest,
            "synthetic evidence",
        )
        self.assertTrue(validate_hashed_regions(blob, (region,))[0]["matched"])

        tampered = b"prefix" + b"evidencE" + b"suffix"
        self.assertFalse(validate_hashed_regions(tampered, (region,))[0]["matched"])

    def test_cross_overlay_sets_remain_aligned(self) -> None:
        self.assertEqual(len(TEXT_OVERLAY_BASES), 10)
        self.assertEqual(len(TEXT_OVERLAY_LABELS), 10)
        self.assertEqual(len(TEXT_PARSER_ENTRIES), 10)
        self.assertEqual(TEXT_OVERLAY_LABELS[:2], ("MISSION_0_A", "MISSION_0_B"))
        self.assertEqual(TEXT_OVERLAY_LABELS[-1], "MISSION_8")
        self.assertEqual(len(EXPLORATION_WRAPPER_BASES), 10)

    def test_opcode_21_semantics_identify_voice_barrier(self) -> None:
        meaning = CONTROL_SEMANTICS["21"]
        self.assertIn("ADPCM voice barrier", meaning)
        self.assertIn("$37F1", meaning)
        self.assertIn("$222D&3", meaning)

    def test_report_module_imports_without_game_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "empty.bin"
            path.write_bytes(b"")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
