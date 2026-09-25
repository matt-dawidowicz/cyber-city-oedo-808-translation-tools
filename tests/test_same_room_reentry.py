from __future__ import annotations

import unittest

from cyber_oedo.runtime.same_room_reentry import analyze_same_room_reentry


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


if __name__ == "__main__":
    unittest.main()
