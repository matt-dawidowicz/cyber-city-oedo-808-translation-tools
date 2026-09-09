"""Verify strict pipeline extraction over the compatibility parser surface."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from cyber_oedo.text.extract_dialogue import main, parse_record


class DialogueExtractionTests(unittest.TestCase):
    """Separate insertion-grade extraction from forensic compatibility mode."""

    def test_pipeline_rejects_unknown_controls_but_keeps_3d_operands(self) -> None:
        """Drop unknown bytecode while retaining text after ``3D 00 06``."""

        valid = (
            b"\x27\x28\x3D\x00\x06"
            + "猫犬猫".encode("shift_jis")
            + b"\x00"
        )
        unknown = (
            b"\x27\x28"
            + "犬猫犬".encode("shift_jis")
            + b"\x33"
            + "猫犬猫".encode("shift_jis")
            + b"\x00"
        )
        payload = valid + b"\xAA" * 8 + unknown

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "payload.bin"
            output = root / "dialogue.tsv"
            source.write_bytes(payload)
            status = main([str(source), str(output)])
            with output.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))

        self.assertEqual(status, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "猫犬猫")
        self.assertEqual(rows[0]["controls"], "3D 00 06")
        self.assertEqual(rows[0]["quality"], "review")

    def test_compatibility_parser_can_still_preserve_unknown_control(self) -> None:
        """Keep old forensic callers able to inspect unknown one-byte values."""

        body = (
            "猫犬".encode("shift_jis")
            + b"\x33"
            + "猫".encode("shift_jis")
            + b"\x00"
        )
        parsed = parse_record(body, 0)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("".join(parsed.text_only), "猫犬猫")
        self.assertEqual(parsed.controls, (0x33,))
        self.assertEqual(parsed.control_opcodes, (0x33,))


if __name__ == "__main__":
    unittest.main()
