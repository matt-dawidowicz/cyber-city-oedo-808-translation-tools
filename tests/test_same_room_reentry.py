from __future__ import annotations

import unittest

from cyber_oedo.runtime.same_room_reentry import analyze_same_room_reentry, direct_absolute_calls


class SameRoomReentryTests(unittest.TestCase):
    def test_requires_authenticated_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "payload SHA-256 mismatch"):
            analyze_same_room_reentry(b"not-the-track-payload")

    def test_report_shape_from_guarded_regions(self) -> None:
        # The full authenticated payload is intentionally not committed.  This
        # regression checks stable policy strings without fabricating disc data.
        from cyber_oedo.runtime.same_room_reentry import _region

        entry = _region("scene_entry_selection")
        self.assertIn("$3702", entry.purpose)
        self.assertIn("always load object and interaction", entry.purpose)

        objects = _region("object_source_initialization")
        self.assertIn("16-byte", objects.purpose)

        rectangles = _region("collision_rectangle_registry")
        self.assertIn("8-byte rectangles", rectangles.purpose)

    def test_direct_absolute_calls_respect_instruction_boundaries(self) -> None:
        blob = bytes.fromhex("A9 20 20 19 55 4C 9E 41 60")
        rows = direct_absolute_calls(blob, 0x1000, 0x4000)
        self.assertEqual(
            rows,
            (
                {"cpu": "$4002", "operation": "JSR", "target": "$5519"},
                {"cpu": "$4005", "operation": "JMP", "target": "$419E"},
            ),
        )

    def test_direct_absolute_calls_exclude_indirect_jumps(self) -> None:
        blob = bytes.fromhex("6C 9E 41 7C 19 55 20 19 55 4C 9E 41")
        rows = direct_absolute_calls(blob, 0x1000, 0x4000)
        self.assertEqual(
            rows,
            (
                {"cpu": "$4006", "operation": "JSR", "target": "$5519"},
                {"cpu": "$4009", "operation": "JMP", "target": "$419E"},
            ),
        )


if __name__ == "__main__":
    unittest.main()
