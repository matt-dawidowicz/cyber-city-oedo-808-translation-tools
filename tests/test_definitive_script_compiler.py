from __future__ import annotations

import unittest

from cyber_oedo.text.definitive_control_anchors import DEFINITIVE_CONTROL_ANCHORS
from cyber_oedo.text.definitive_script_compiler import (
    DefinitiveScriptRow,
    compile_direct_row,
    compile_direct_rows,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable


class DefinitiveScriptCompilerTests(unittest.TestCase):
    def _glyphs(self, *entry_ids: str) -> EnglishGlyphTable:
        return EnglishGlyphTable.from_texts(
            fragment
            for entry_id in entry_ids
            for fragment in DEFINITIVE_CONTROL_ANCHORS[entry_id]
        )

    def test_timed_wait_release_path_uses_frozen_anchor(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "あ".encode("shift_jis")
            + bytes((0x2F,))
            + "い".encode("shift_jis")
            + bytes((0x2F,))
            + "う".encode("shift_jis")
            + bytes((0x00,))
        )
        row = DefinitiveScriptRow(
            entry_id="T00381",
            bank="MISSION_0",
            category="Spoken dialogue",
            resource="BILL4",
            offset=0,
            japanese_source="あいう",
            english=" ".join(DEFINITIVE_CONTROL_ANCHORS["T00381"]),
        )
        compiled = compile_direct_row(source, row, self._glyphs("T00381"))
        self.assertEqual(compiled.status, "anchored")
        self.assertIsNotNone(compiled.compiled_record)
        self.assertEqual(compiled.compiled_record.count(bytes((0x2F,))), 2)

    def test_changed_english_cannot_silently_use_stale_anchors(self) -> None:
        source = (
            bytes.fromhex("27 28")
            + "あ".encode("shift_jis")
            + bytes((0x2F,))
            + "い".encode("shift_jis")
            + bytes((0x2F,))
            + "う".encode("shift_jis")
            + bytes((0x00,))
        )
        row = DefinitiveScriptRow(
            entry_id="T00381",
            bank="MISSION_0",
            category="Spoken dialogue",
            resource="BILL4",
            offset=0,
            japanese_source="あいう",
            english="This is a new translation, not the frozen old version.",
        )
        compiled = compile_direct_row(source, row, self._glyphs("T00381"))
        self.assertEqual(compiled.status, "anchor_text_mismatch")
        self.assertIsNone(compiled.compiled_record)

    def test_t00604_and_t00605_compile_as_one_physical_record(self) -> None:
        owner_text = "俺は少し待ってみることにした……。"
        continuation_text = "「ずいぶん無口なのね」"
        marker_offset = 0x00177DA8
        record = (
            bytes.fromhex("27 28")
            + owner_text.encode("shift_jis")
            + bytes.fromhex("40 3D 00 06")
            + continuation_text.encode("shift_jis")
            + bytes((0x00,))
        )
        payload = bytearray(marker_offset + len(record))
        payload[marker_offset : marker_offset + len(record)] = record

        owner = DefinitiveScriptRow(
            entry_id="T00604",
            bank="MISSION_0",
            category="Narration / description",
            resource="KURUZER",
            offset=marker_offset,
            japanese_source=owner_text,
            english="I waited a while...",
        )
        continuation = DefinitiveScriptRow(
            entry_id="T00605",
            bank="MISSION_0",
            category="Auxiliary cutscene / system text",
            resource="KURUZER",
            offset=0x00177DD0,
            japanese_source=continuation_text,
            english="‘You're awfully quiet.’",
        )
        compiled = compile_direct_rows(
            bytes(payload),
            (owner, continuation),
            self._glyphs("T00604"),
        )
        self.assertEqual(compiled[0].status, "composite_anchored")
        self.assertEqual(compiled[1].status, "composite_continuation")
        self.assertIsNotNone(compiled[0].compiled_record)
        self.assertIn(bytes.fromhex("3D 00 06"), compiled[0].compiled_record)


if __name__ == "__main__":
    unittest.main()
