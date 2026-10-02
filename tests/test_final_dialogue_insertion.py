from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cyber_oedo.text.final_dialogue_insertion import (
    FinalDialogueRow,
    audit_row,
    build_in_place_patches,
    load_final_dialogue_tsv,
    summarize_audit,
)
from cyber_oedo.text.packed_english import PackedEnglishDictionary
from cyber_oedo.runtime.packed_english_runtime import compact_repertoire_for_texts

class FinalDialogueInsertionTests(unittest.TestCase):
    def _dictionary(self, *texts: str) -> PackedEnglishDictionary:
        rep = compact_repertoire_for_texts(texts)
        return PackedEnglishDictionary.from_texts(texts, repertoire=rep)

    def test_authenticated_row_can_patch_in_place(self) -> None:
        row = FinalDialogueRow("T1","MISSION_0","Spoken dialogue","TEST",0,"あ","Hi")
        payload = bytes.fromhex("27 28 82 A0 00")
        dictionary = self._dictionary("Hi")
        audit = audit_row(payload, row, dictionary)
        self.assertTrue(audit.can_patch_in_place)
        patches = build_in_place_patches(payload, (row,), dictionary)
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0].offset, 2)
        self.assertEqual(patches[0].expected, bytes.fromhex("82 A0"))

    def test_growth_is_explicitly_relocation_required(self) -> None:
        row = FinalDialogueRow("T2","MISSION_0","Narration / description","TEST",0,"あ","Longer")
        payload = bytes.fromhex("27 28 82 A0 00")
        dictionary = self._dictionary("Longer")
        audit = audit_row(payload, row, dictionary)
        self.assertTrue(audit.needs_relocation)
        self.assertEqual(build_in_place_patches(payload, (row,), dictionary), ())

    def test_shorter_text_is_padding_candidate_and_not_default_patched(self) -> None:\n        row = FinalDialogueRow("T4","MISSION_0","Spoken dialogue","TEST",0,"あいう","Hi")\n        payload = bytes.fromhex("27 28 82 A0 82 A2 82 A4 00")\n        dictionary = self._dictionary("Hi")\n        audit = audit_row(payload, row, dictionary)\n        self.assertTrue(audit.is_padding_candidate)\n        self.assertEqual(build_in_place_patches(payload, (row,), dictionary), ())\n        self.assertEqual(\n            len(build_in_place_patches(\n                payload, (row,), dictionary, allow_padding_candidates=True\n            )),\n            1,\n        )\n\n    def test_wrong_binary_mapping_never_patches(self) -> None:
        row = FinalDialogueRow("T3","MISSION_1","Spoken dialogue","TEST",0,"あ","Hi")
        dictionary = self._dictionary("Hi")
        audit = audit_row(bytes.fromhex("27 28 82 A2 00"), row, dictionary)
        self.assertEqual(audit.status, "mapping_required")

    def test_tsv_loader_rejects_duplicate_ids(self) -> None:
        text = (
            "ID\tBank\tCategory\tResource\tOffset\tJapanese Source\tFinal Localization\n"
            "T1\tMISSION_0\tSpoken dialogue\tTEST\t0x0\tあ\tHi\n"
            "T1\tMISSION_0\tSpoken dialogue\tTEST\t0x0\tあ\tHi\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dialogue.tsv"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_final_dialogue_tsv(path)

    def test_summary_keeps_unsolved_rows_visible(self) -> None:
        dictionary = self._dictionary("Hi", "Longer")
        rows = (
            FinalDialogueRow("T1","MISSION_0","Spoken dialogue","A",0,"あ","Hi"),
            FinalDialogueRow("T2","MISSION_0","Spoken dialogue","B",5,"あ","Longer"),
        )
        payload = bytes.fromhex("27 28 82 A0 00 27 28 82 A0 00")
        audits = tuple(audit_row(payload, row, dictionary) for row in rows)
        summary = summarize_audit(audits)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["exact_footprint"], 1)
        self.assertEqual(summary["relocation_required"], 1)

if __name__ == "__main__":
    unittest.main()
