from __future__ import annotations

import unittest

from cyber_oedo.script import event

GLYPH = b"\x82\xa0"


def record(glyphs: int) -> bytes:
    return b"\x27\x28" + GLYPH * glyphs + b"\x00"


def be(value: int) -> bytes:
    return (value & 0xFFFF).to_bytes(2, "big")


def synthetic_body() -> tuple[bytes, dict[str, int]]:
    """Build a body with every offset kind the relinker must rewrite."""

    entries_end = 3 * event.ENTRY_SIZE
    labels = b"\x00" + GLYPH * 6 + b"\x00"  # 14-byte label slot
    script = entries_end + len(labels)
    marks: dict[str, int] = {"labels": entries_end, "script": script}

    # handler 1
    out = bytearray()
    out += b"\x24\x03\x00\x01\x26"            # IF imm 1
    if_field = len(out)
    out += b"\0\0"
    marks["a"] = script + len(out)
    out += record(2)                         # skipped when false
    if_target = len(out)
    out += b"\x2D"
    goto_field = len(out)
    out += b"\0\0"
    out += b"\x48\x03\x00\x01\x03\x00\x02\x03\x00\x44"  # 48 with third value
    out += b"\x48\x03\x00\x01\x03\x00\x01"               # 48 without
    out += b"\x32\x00\x01\x00"                # choice, last index 1 -> 2 blocks
    for name, glyphs in (("b", 3), ("c", 1)):
        block = record(glyphs)
        marks[name] = script + len(out) + 2
        out += be(len(block)) + block
    goto_target = len(out)
    out += b"\x00"                           # end handler 1
    marks["handler2"] = script + len(out)
    marks["d"] = script + len(out)
    out += record(4) + b"\x00"
    out[if_field:if_field + 2] = be(if_target - (if_field + 2))
    out[goto_field:goto_field + 2] = be(goto_target - (goto_field + 2))

    body = bytearray()
    for prefix, target in (
        (event.SCRIPT_ENTRY_PREFIX, script),
        (b"\x00\x05\x00\x00\x05", marks["handler2"]),
        (b"\x00\x00\x00\x00\x00", entries_end),
    ):
        field = len(body) + event.ENTRY_OFFSET_FIELD
        body += prefix + be(target - field)
    body += labels + out + b"\x27\x28\x82"  # cut-off stale alignment tail
    return bytes(body), marks


class EventParseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.body, self.marks = synthetic_body()
        self.layout = event.parse_event_body(self.body)

    def test_finds_structure_and_every_offset_kind(self) -> None:
        layout = self.layout
        self.assertEqual(layout.script_start, self.marks["script"])
        self.assertEqual(layout.label_start, self.marks["labels"])
        self.assertEqual(
            [span.start for span in layout.dialogue],
            [self.marks[name] for name in ("a", "b", "c", "d")],
        )
        kinds = sorted(row.kind for row in layout.offsets)
        self.assertEqual(kinds, ["choice", "choice", "entry", "entry", "goto", "if", "labels"])
        self.assertEqual(self.body[layout.tail_start:], b"\x27\x28\x82")

    def test_unchanged_relink_is_byte_identical(self) -> None:
        self.assertEqual(event.replace_dialogue(self.layout, {}), self.body)

    def test_growth_keeps_every_offset_on_its_command(self) -> None:
        grown = {self.marks["a"]: record(40), self.marks["b"]: record(25)}
        new = event.replace_dialogue(self.layout, grown)
        relinked = event.parse_event_body(new)
        delta_a = len(record(40)) - len(record(2))
        delta_b = len(record(25)) - len(record(3))

        def moved(position: int) -> int:
            shift = delta_a if position >= self.marks["a"] + len(record(2)) else 0
            if position >= self.marks["b"] + len(record(3)):
                shift += delta_b
            return position + shift

        before = {moved(row.field): (moved(row.target), row.kind) for row in self.layout.offsets}
        after = {row.field: (row.target, row.kind) for row in relinked.offsets}
        self.assertEqual(before, after)
        self.assertEqual(new[relinked.tail_start:], b"\x27\x28\x82")

    def test_doubled_dialogue_round_trips_through_rebuild(self) -> None:
        resource = b"H" * 16 + self.body
        rebuilt = event.rebuild_event_resource(resource, event.doubled_dialogue(self.layout))
        self.assertEqual(rebuilt[:16], b"H" * 16)
        relinked = event.parse_event_resource(rebuilt)
        self.assertEqual(len(relinked.dialogue), 4)

    def test_run_on_doubling_has_no_page_wait(self) -> None:
        start = self.marks["a"]
        paged = event.doubled_dialogue(self.layout)[start]
        run_on = event.doubled_dialogue(self.layout, page_break=False)[start]
        self.assertEqual(paged, b"\x27\x28" + GLYPH * 2 + b"\x40" + GLYPH * 2 + b"\x00")
        self.assertEqual(run_on, b"\x27\x28" + GLYPH * 4 + b"\x00")


class EventParseErrorTests(unittest.TestCase):
    def test_unknown_opcode_fails_closed(self) -> None:
        body, marks = synthetic_body()
        broken = bytearray(body)
        broken[marks["script"]] = 0x99
        with self.assertRaisesRegex(event.EventScriptError, "unknown event opcode 0x99"):
            event.parse_event_body(bytes(broken))

    def test_variable_dependent_48_is_rejected(self) -> None:
        body, marks = synthetic_body()
        broken = bytearray(body)
        start = body.index(b"\x48\x03\x00\x01\x03\x00\x02")
        broken[start + 4] = event.VARIABLE_TAG
        with self.assertRaisesRegex(event.EventScriptError, "variable-dependent"):
            event.parse_event_body(bytes(broken))

    def test_replacement_must_be_a_whole_record_at_a_known_start(self) -> None:
        body, marks = synthetic_body()
        layout = event.parse_event_body(body)
        with self.assertRaisesRegex(event.EventScriptError, "no dialogue record"):
            event.replace_dialogue(layout, {marks["a"] + 1: record(1)})
        with self.assertRaisesRegex(event.EventScriptError, "not a 27 28"):
            event.replace_dialogue(layout, {marks["a"]: b"\x27\x28\x82\xa0"})

    def test_interpreter_guards_fail_closed(self) -> None:
        last = max(cpu + len(expected) for _, cpu, expected in event.INTERPRETER_GUARDS)
        payload = bytearray(event.MISSION0_B_MODULE_BASE + last)
        for _, cpu, expected in event.INTERPRETER_GUARDS:
            start = event.MISSION0_B_MODULE_BASE + cpu
            payload[start : start + len(expected)] = expected
        event.verify_event_interpreter(payload)
        payload[event.MISSION0_B_MODULE_BASE + 0x94E2] ^= 0xFF
        with self.assertRaisesRegex(event.EventScriptError, "IF handler"):
            event.verify_event_interpreter(payload)


if __name__ == "__main__":
    unittest.main()
