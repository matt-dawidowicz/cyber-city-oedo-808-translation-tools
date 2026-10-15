from __future__ import annotations

import unittest

from cyber_oedo.runtime.whole_game import (
    ADPCM_PROVEN_RECORDS,
    ADPCM_RECORD_BYTES,
    SAVE_FILE_DESCRIPTOR,
    MISSION_SCRIPT_OPCODES,
    SAVE_SLOT_BYTES,
    TRACK2_START_LBA,
    LIVE_CAPTURE_POST_GUARDS,
    live_capture_post_guard_report,
    _decode_cd_descriptor,
    _decode_adpcm_record,
    _object_and_interaction_report,
)


class WholeGameProofTests(unittest.TestCase):
    def test_post_operation_capture_guards_require_authenticated_bytes(self) -> None:
        length = max(offset + len(signature) for _, offset, signature
                     in LIVE_CAPTURE_POST_GUARDS)
        payload = bytearray(length)
        for _, offset, signature in LIVE_CAPTURE_POST_GUARDS:
            payload[offset:offset + len(signature)] = signature
        report = live_capture_post_guard_report(payload)
        self.assertTrue(all(row["matched"] for row in report))
        self.assertEqual({row["name"] for row in report}, {
            "interaction_copy_completed", "object_init_completed",
            "object_frame_update_completed", "startup_bm_read_return",
            "mission_bm_read_return", "outer_event_entry",
        })
        payload[LIVE_CAPTURE_POST_GUARDS[0][1]] ^= 1
        report = live_capture_post_guard_report(payload)
        self.assertFalse(report[0]["matched"])
        self.assertTrue(all(row["matched"] for row in report[1:]))

    def test_save_file_shape_is_four_one_byte_slots(self) -> None:
        self.assertEqual(SAVE_SLOT_BYTES, 4)
        self.assertEqual(SAVE_FILE_DESCRIPTOR[:2], b"\x07\x00")
        self.assertEqual(SAVE_FILE_DESCRIPTOR[2:], b"OEDO808   ")



    def test_mission_script_opcode_set_is_explicit(self) -> None:
        self.assertEqual(len(MISSION_SCRIPT_OPCODES), 27)
        self.assertIn(0x49, MISSION_SCRIPT_OPCODES)
        self.assertEqual(MISSION_SCRIPT_OPCODES[-1], 0x4C)

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
