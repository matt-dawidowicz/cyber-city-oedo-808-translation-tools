from __future__ import annotations

import unittest

from cyber_oedo.runtime.whole_game import (
    ADPCM_PROVEN_RECORDS,
    ADPCM_RECORD_BYTES,
    SAVE_FILE_DESCRIPTOR,
    SAVE_SLOT_BYTES,
    TRACK2_START_LBA,
    _decode_cd_descriptor,
    _decode_adpcm_record,
    _object_and_interaction_report,
)


class WholeGameProofTests(unittest.TestCase):
    def test_save_file_shape_is_four_one_byte_slots(self) -> None:
        self.assertEqual(SAVE_SLOT_BYTES, 4)
        self.assertEqual(SAVE_FILE_DESCRIPTOR[:2], b"\x07\x00")
        self.assertEqual(SAVE_FILE_DESCRIPTOR[2:], b"OEDO808   ")


    def test_event_cd_descriptor_uses_absolute_disc_lba(self) -> None:
        row = _decode_cd_descriptor(bytes.fromhex("00 71 10 0C"), 0)
        self.assertEqual(TRACK2_START_LBA, 3590)
        self.assertEqual(row["absolute_lba"], "0x001071")
        self.assertEqual(row["track2_relative_sector"], 0x1071 - 3590)
        self.assertEqual(row["block_count"], 0x0C)

    def test_adpcm_record_is_six_bytes(self) -> None:
        row = _decode_adpcm_record(bytes.fromhex("01 8A 50 0D 10 67"), 1)
        self.assertEqual(ADPCM_RECORD_BYTES, 6)
        self.assertEqual(row["sample_id"], 1)
        self.assertEqual(row["transfer"]["cl"], 0x01)
        self.assertEqual(row["transfer"]["dl"], 0x8A)
        self.assertEqual(row["transfer"]["ch"], 0x50)
        self.assertEqual(row["transfer"]["block_count"], 0x0D)
        self.assertEqual(row["playback_length"], 0x6710)
        self.assertEqual(row["sample_rate_code"], 0x0E)
        self.assertGreaterEqual(ADPCM_PROVEN_RECORDS, 64)

    def test_object_layout_keeps_unproven_fields_opaque(self) -> None:
        report = _object_and_interaction_report()
        fields = report["live_object_record"]["fields"]
        self.assertEqual(fields["+7"], "animation countdown")
        self.assertEqual(fields["+8/+9"], "animation-script pointer")
        self.assertIn("preserved but not read", fields["+11/+12"])
        self.assertIn("reserved", fields["+15"])

    def test_interaction_progress_handoff_is_decoded(self) -> None:
        report = _object_and_interaction_report()
        fields = report["interaction_result"]["local_consumers"]
        self.assertIn("$371F = value-$10", fields["+6 ($3709)"])
        self.assertIn("not read", fields["+4/+5"])
        self.assertIn("not read", fields["+7/+8"])


if __name__ == "__main__":
    unittest.main()
