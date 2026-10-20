from __future__ import annotations

import unittest

from cyber_oedo.runtime.dialogue_load_architecture import TRACK2_START_LBA
from cyber_oedo.runtime.text_engine_completion import (
    INFORMATION_COMMAND_SEMANTICS,
    INFORMATION_PARSER_COPY_OFFSETS,
    RESOURCE_DESCRIPTOR_BYTES,
    RESOURCE_NAME_BYTES,
    count_direct_shift_jis_strings,
    decode_information_stream,
    parse_resource_descriptor_table,
)


class TextEngineCompletionTests(unittest.TestCase):
    def test_information_stream_decodes_positioned_text_and_controls(self) -> None:
        blob = (
            bytes((2, 1, 5, 1, 6, 0, 0, 0x50))
            + bytes((0, 1, 3))
            + "情報".encode("shift_jis")
            + b"\x00"
            + bytes((8, 7, 0, 20, 8, 11, 9, 9, 3))
        )
        commands, end = decode_information_stream(blob)
        self.assertEqual(end, len(blob))
        self.assertEqual(commands[0]["name"], "set_glyph_delay")
        self.assertEqual(commands[3]["name"], "positioned_shift_jis")
        self.assertEqual(commands[3]["x"], 1)
        self.assertEqual(commands[3]["y"], 3)
        self.assertEqual(commands[3]["text"], "情報")
        rectangle = next(item for item in commands if item["opcode"] == 7)
        self.assertEqual(
            (rectangle["mode"], rectangle["x"], rectangle["y"]),
            (0, 20, 8),
        )
        self.assertEqual((rectangle["width"], rectangle["height"]), (11, 9))
        self.assertEqual(commands[-2]["name"], "wait_for_input")
        self.assertEqual(commands[-1]["name"], "terminate")

    def test_information_stream_rejects_unknown_opcode(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported information opcode"):
            decode_information_stream(bytes((0x0B,)))

    def test_descriptor_schema_is_16_bytes(self) -> None:
        payload = bytearray(0x8000)
        record = bytearray(16)
        record[:10] = b"INVENTRY\x00"
        record[10:12] = (TRACK2_START_LBA + 3).to_bytes(2, "little")
        record[12] = 2
        record[13:16] = (0x0890).to_bytes(3, "little")
        payload[:16] = record

        rows = parse_resource_descriptor_table(bytes(payload), "TEST", 0)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.name, "INVENTRY")
        self.assertEqual(row.sector, TRACK2_START_LBA + 3)
        self.assertEqual(row.sector_span, 2)
        self.assertEqual(row.byte_length, 0x0890)
        self.assertEqual(row.payload_offset, 3 * 2048)
        self.assertEqual(RESOURCE_DESCRIPTOR_BYTES, 16)
        self.assertEqual(RESOURCE_NAME_BYTES, 10)

    def test_descriptor_parser_stops_at_non_descriptor_data(self) -> None:
        payload = bytearray(0x5000)
        record = bytearray(16)
        record[:10] = b"SHIRYO\x00\x00\x00\x00"
        record[10:12] = (TRACK2_START_LBA + 2).to_bytes(2, "little")
        record[12] = 1
        record[13:16] = (320).to_bytes(3, "little")
        payload[:16] = record
        payload[16:32] = b"\x00\x0c" + b"\x00" * 14
        self.assertEqual(
            len(parse_resource_descriptor_table(bytes(payload), "TEST", 0)),
            1,
        )

    def test_direct_shift_jis_audit_is_conservative(self) -> None:
        binary = bytes(range(64)) + b"\x00" * 32
        text = "捜査モード".encode("shift_jis") + b"\x00"
        self.assertEqual(count_direct_shift_jis_strings(binary), 0)
        self.assertGreaterEqual(count_direct_shift_jis_strings(text), 1)

    def test_shared_information_parser_copy_set_is_explicit(self) -> None:
        self.assertEqual(len(INFORMATION_PARSER_COPY_OFFSETS), 8)
        self.assertIn(8, INFORMATION_COMMAND_SEMANTICS)
        self.assertIn("ADPCM", INFORMATION_COMMAND_SEMANTICS[8])


if __name__ == "__main__":
    unittest.main()
