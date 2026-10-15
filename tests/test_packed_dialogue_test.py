from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cyber_oedo.build.packed_dialogue_test import (
    TRACK2_PAYLOAD_SHA256,
    load_mission0b_evidence,
    optional_opening_menu_patches,
    verify_nonoverlapping_patches,
)
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.text.final_dialogue_insertion import FinalDialogueRow


class PackedDialogueProofGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = (
            FinalDialogueRow("T1", "MISSION_0", "Spoken dialogue", "BAR", 0, "あ", "Hi"),
            FinalDialogueRow("T2", "MISSION_1", "Spoken dialogue", "OTHER", 5, "い", "Bye"),
        )

    def _read(self, data: dict) -> frozenset[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "runtime_evidence.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_mission0b_evidence(path, self.rows)

    def _evidence(self) -> dict:
        return {
            "source_payload_sha256": TRACK2_PAYLOAD_SHA256,
            "runtime_overlay": "MISSION_0_B",
            "entry_ids": ["T1"],
            "runtime_traces": {"T1": "Mesen capture: MPR2/MPR3 and parser entry"},
        }

    def test_requires_external_m0b_evidence_before_building(self) -> None:
        with self.assertRaisesRegex(ValueError, "--mission0b-evidence"):
            load_mission0b_evidence(None, self.rows)

    def test_scoped_evidence_accepts_only_selected_m0b_ids(self) -> None:
        self.assertEqual(self._read(self._evidence()), frozenset({"T1"}))

    def test_wrong_overlay_and_source_are_rejected(self) -> None:
        for field, bad_value in (
            ("runtime_overlay", "MISSION_0_A"),
            ("source_payload_sha256", "0" * 64),
        ):
            evidence = self._evidence()
            evidence[field] = bad_value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self._read(evidence)

    def test_unsupported_ids_or_missing_trace_cannot_be_patched(self) -> None:
        for bad_id in ("T2", "T404"):
            evidence = self._evidence()
            evidence["entry_ids"] = [bad_id]
            with self.subTest(entry_id=bad_id):
                with self.assertRaises(ValueError):
                    self._read(evidence)
        evidence = self._evidence()
        evidence["runtime_traces"] = {}
        with self.assertRaisesRegex(ValueError, "trace"):
            self._read(evidence)

    def test_menu_is_opt_in_and_invoked_with_explicit_audio_track(self) -> None:
        sentinel = (PayloadPatch(100, b"x", b"y", "menu"),)
        with patch(
            "cyber_oedo.build.packed_dialogue_test.build_opening_menu_patches",
            return_value=sentinel,
        ) as mocked:
            self.assertEqual(
                optional_opening_menu_patches(b"", enable=False, audio_track=3), ()
            )
            mocked.assert_not_called()
            self.assertEqual(
                optional_opening_menu_patches(b"input", enable=True, audio_track=3),
                sentinel,
            )
            mocked.assert_called_once_with(b"input", audio_track=3)

    def test_source_patch_overlap_fails_closed(self) -> None:
        a = PayloadPatch(5, b"abc", b"ABC", "renderer")
        b = PayloadPatch(7, b"xy", b"XY", "menu")
        with self.assertRaisesRegex(ValueError, "overlapping"):
            verify_nonoverlapping_patches((b, a))
        verify_nonoverlapping_patches((a, PayloadPatch(8, b"xx", b"YY", "text")))


if __name__ == "__main__":
    unittest.main()
