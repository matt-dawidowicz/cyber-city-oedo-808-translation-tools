from __future__ import annotations

import unittest

from cyber_oedo.runtime.state_diff import SnapshotState, compare_states, physical_address


class StateDiffTests(unittest.TestCase):
    def test_reports_contiguous_runs_and_mpr_changes(self) -> None:
        before_memory = bytearray(0x10000)
        after_memory = bytearray(before_memory)
        after_memory[0x2100:0x2102] = b"\x34\x12"
        after_memory[0x4000] = 0x80

        before = SnapshotState(
            label="idle",
            mprs=(0xFF, 0xF8, 0x00, 0x81, 0x82, 0x83, 0x84, 0x00),
            memory=bytes(before_memory),
        )
        after = SnapshotState(
            label="right-held",
            mprs=(0xFF, 0xF8, 0x00, 0x81, 0x82, 0x90, 0x84, 0x00),
            memory=bytes(after_memory),
        )

        report = compare_states(before, after)
        self.assertEqual(report["changed_bytes"], 3)
        self.assertEqual(report["changed_runs"], 2)
        self.assertEqual(report["runs"][0]["start"], "0x2100")
        self.assertEqual(report["runs"][0]["end_exclusive"], "0x2102")
        self.assertEqual(report["runs"][0]["before_hex"], "0000")
        self.assertEqual(report["runs"][0]["after_hex"], "3412")
        self.assertEqual(report["mpr_changes"][0]["slot"], 5)

    def test_formats_physical_address_from_correct_window(self) -> None:
        mprs = (0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17)
        self.assertEqual(physical_address(0x4001, mprs), "*12:0001")
        self.assertEqual(physical_address(0xBFFF, mprs), "*15:1FFF")

    def test_truncation_is_explicit(self) -> None:
        before_memory = bytes(0x10000)
        after_memory = bytearray(before_memory)
        after_memory[0x0100] = 1
        after_memory[0x0200] = 2
        state = (0,) * 8
        report = compare_states(
            SnapshotState("before", state, before_memory),
            SnapshotState("after", state, bytes(after_memory)),
            max_runs=1,
        )
        self.assertTrue(report["truncated"])
        self.assertEqual(report["reported_runs"], 1)
        self.assertEqual(report["changed_runs"], 2)


if __name__ == "__main__":
    unittest.main()
