"""Verify Tier-A opcode-aware dialogue structure and round trips."""

from __future__ import annotations

import unittest

from cyber_oedo.script import (
    ControlCommand,
    DialogueOpcode,
    parse_dialogue_body,
    parse_dialogue_record,
    serialize_dialogue_body,
    serialize_dialogue_record,
)
from cyber_oedo.text.extract_dialogue import parse_record


class DialogueStructureTests(unittest.TestCase):
    """Exercise structured command parsing independently of game media."""

    def test_round_trip_preserves_operand_zero_inside_3d(self) -> None:
        """Keep a zero operand from being mistaken for record termination."""

        source = (
            b"\x27\x28"
            + "猫".encode("shift_jis")
            + b"\x3d\x00\x06"
            + "犬".encode("shift_jis")
            + b"\x40"
            + "終".encode("shift_jis")
            + b"\x00"
        )
        record = parse_dialogue_record(source, 0)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.body.visible_text, "猫犬終")
        self.assertEqual(
            record.body.control_opcodes,
            (
                int(DialogueOpcode.INDIRECT_TEXT),
                int(DialogueOpcode.PAGE_BREAK),
            ),
        )
        indirect = record.body.commands[0]
        self.assertEqual(indirect.operands, b"\x00\x06")
        self.assertEqual(indirect.name, "indirect_text")
        self.assertEqual(record.end_offset, len(source) - 1)
        self.assertEqual(serialize_dialogue_record(record), source)

    def test_zero_operands_of_one_byte_commands_are_data(self) -> None:
        """Consume zero bytes as operands of ``2A`` and ``7E`` commands."""

        source = (
            "前".encode("shift_jis")
            + b"\x2a\x00"
            + "中".encode("shift_jis")
            + b"\x7e\x00"
            + "後".encode("shift_jis")
            + b"\x00"
        )
        body = parse_dialogue_body(source, 0)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(body.visible_text, "前中後")
        self.assertEqual(body.control_opcodes, (0x2A, 0x7E))
        self.assertEqual(
            [command.operands for command in body.commands],
            [b"\x00", b"\x00"],
        )
        self.assertEqual(serialize_dialogue_body(body), source)

    def test_known_zero_operand_controls_round_trip(self) -> None:
        """Preserve the established zero-operand command sequence."""

        source = (
            "猫".encode("shift_jis")
            + b"\x21\x2f\x40\x5c"
            + "犬".encode("shift_jis")
            + b"\x00"
        )
        body = parse_dialogue_body(source, 0)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(
            body.control_opcodes,
            (0x21, 0x2F, 0x40, 0x5C),
        )
        self.assertEqual(serialize_dialogue_body(body), source)

    def test_unknown_control_is_strict_by_default(self) -> None:
        """Reject unknown command shapes unless forensic mode opts in."""

        source = "猫".encode("shift_jis") + b"\x33" + "犬".encode("shift_jis") + b"\x00"
        self.assertIsNone(parse_dialogue_body(source, 0))
        permissive = parse_dialogue_body(
            source,
            0,
            allow_unknown_controls=True,
        )
        self.assertIsNotNone(permissive)
        assert permissive is not None
        command = permissive.commands[0]
        self.assertIsInstance(command, ControlCommand)
        self.assertFalse(command.is_known)
        self.assertEqual(serialize_dialogue_body(permissive), source)

    def test_truncated_operand_is_rejected(self) -> None:
        """Reject commands whose declared operands are incomplete."""

        self.assertIsNone(parse_dialogue_body(b"\x3d\x00", 0))
        self.assertIsNone(parse_dialogue_body(b"\x2a", 0))

    def test_missing_or_wrong_marker_is_rejected(self) -> None:
        """Require the complete, exact two-byte dialogue marker."""

        self.assertIsNone(parse_dialogue_record(b"\x27", 0))
        self.assertIsNone(parse_dialogue_record(b"\x27\x29\x00", 0))

    def test_semantic_and_legacy_tags_keep_operand_evidence(self) -> None:
        """Expose typed and legacy audit views from the same parsed command."""

        source = b"\x3d\x00\x06" + "猫".encode("shift_jis") + b"\x00"
        body = parse_dialogue_body(source, 0)
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(body.tagged_text, "<$3D:00 06>猫")
        self.assertEqual(
            body.legacy_tagged_text,
            "<$3D><$00><$06>猫",
        )
        self.assertEqual(
            body.legacy_control_bytes,
            (0x3D, 0x00, 0x06),
        )

    def test_offsets_are_contiguous_and_source_accurate(self) -> None:
        """Retain source offsets for every typed node and terminator."""

        prefix = b"xxxx"
        source = (
            prefix
            + "猫".encode("shift_jis")
            + b"\x40"
            + "犬".encode("shift_jis")
            + b"\x00"
        )
        body = parse_dialogue_body(source, len(prefix))
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(body.nodes[0].offset, len(prefix))
        self.assertEqual(body.nodes[1].offset, len(prefix) + 2)
        self.assertEqual(body.terminator_offset, len(source) - 1)

    def test_legacy_projection_keeps_existing_page_control_shape(self) -> None:
        """Keep the v1 extractor token shape for ordinary page controls."""

        data = "猫".encode("shift_jis") + b"\x40" + "犬".encode("shift_jis") + b"\x00"
        parsed = parse_record(data, 0)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("".join(parsed.text_only), "猫犬")
        self.assertEqual("".join(parsed.tokens), "猫<$40>犬")
        self.assertEqual(parsed.controls, (0x40,))

    def test_legacy_projection_recovers_text_after_3d_zero(self) -> None:
        """Expose text after a zero-valued operand through the old API."""

        data = b"\x3d\x00\x06" + "猫犬".encode("shift_jis") + b"\x00"
        parsed = parse_record(data, 0)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("".join(parsed.text_only), "猫犬")
        self.assertEqual(
            "".join(parsed.tokens),
            "<$3D><$00><$06>猫犬",
        )
        self.assertEqual(parsed.controls, (0x3D, 0x00, 0x06))
        self.assertEqual(parsed.end_offset, len(data) - 1)


if __name__ == "__main__":
    unittest.main()
