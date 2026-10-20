from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from cyber_oedo.text.final_dialogue_insertion import (
    FinalDialogueRow,
    audit_row,
    build_in_place_patches,
    load_final_dialogue_tsv,
    load_authenticated_dialogue_master,
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

    def test_overlay_evidence_allowlist_excludes_unproven_entries(self) -> None:
        row = FinalDialogueRow("T1", "MISSION_0", "Spoken dialogue", "TEST", 0, "あ", "Hi")
        payload = bytes.fromhex("27 28 82 A0 00")
        dictionary = self._dictionary("Hi")
        self.assertEqual(
            build_in_place_patches(
                payload, (row,), dictionary,
                allowed_entry_ids=frozenset(),
            ),
            (),
        )
        self.assertEqual(
            len(build_in_place_patches(
                payload, (row,), dictionary,
                allowed_banks=frozenset({"MISSION_0"}),
                allowed_entry_ids=frozenset({"T1"}),
            )),
            1,
        )

    def test_definitive_master_is_authenticated_and_normalized(self) -> None:
        content = (
            "ID\tBank\tCategory\tResource\tOffset\tJapanese Source"
            "\tDefinitive Localization\tQuality\n"
            "T1\tMISSION_0\tSpoken dialogue\tBAR\t0x0\tあ\tLatest English\tverified\n"
            "T2\tMISSION_1\tCommand UI\tUI\t0x10\tい\tMenu\tverified\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "definitive.tsv"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                load_authenticated_dialogue_master(path, edition="definitive")
            import hashlib

            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch(
                "cyber_oedo.text.final_dialogue_insertion.DEFINITIVE_SCRIPT_TSV_SHA256",
                digest,
            ):
                rows = load_authenticated_dialogue_master(path, edition="definitive")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].entry_id, "T1")
            self.assertEqual(rows[0].english, "Latest English")

    def test_legacy_and_definitive_hashes_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "unreviewed.tsv"
            path.write_text("arbitrary text", encoding="utf-8")
            for edition in ("legacy", "definitive"):
                with self.subTest(edition=edition):
                    with self.assertRaisesRegex(ValueError, "SHA-256"):
                        load_authenticated_dialogue_master(path, edition=edition)

    def test_growth_is_explicitly_relocation_required(self) -> None:
        row = FinalDialogueRow("T2","MISSION_0","Narration / description","TEST",0,"あ","Longer")
        payload = bytes.fromhex("27 28 82 A0 00")
        dictionary = self._dictionary("Longer")
        audit = audit_row(payload, row, dictionary)
        self.assertTrue(audit.needs_relocation)
        self.assertEqual(build_in_place_patches(payload, (row,), dictionary), ())

    def test_shorter_text_is_padding_candidate_and_not_default_patched(self) -> None:
        row = FinalDialogueRow(
            "T4", "MISSION_0", "Spoken dialogue", "TEST", 0, "あいう", "Hi"
        )
        payload = bytes.fromhex("27 28 82 A0 82 A2 82 A4 00")
        dictionary = self._dictionary("Hi")
        audit = audit_row(payload, row, dictionary)
        self.assertTrue(audit.is_padding_candidate)
        self.assertEqual(build_in_place_patches(payload, (row,), dictionary), ())
        self.assertEqual(
            len(
                build_in_place_patches(
                    payload,
                    (row,),
                    dictionary,
                    allow_padding_candidates=True,
                )
            ),
            1,
        )

    def test_wrong_binary_mapping_never_patches(self) -> None:
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
