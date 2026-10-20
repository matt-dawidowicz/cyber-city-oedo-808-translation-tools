from __future__ import annotations

import unittest

from cyber_oedo.text.composite_dialogue_records import (
    BY_OWNER_ID,
    COMPOSITE_DIALOGUE_RECORDS,
    CONTINUATION_IDS,
)


class CompositeDialogueRecordTests(unittest.TestCase):
    def test_expected_composite_records_are_registered(self) -> None:
        self.assertEqual(
            tuple(item.owner_id for item in COMPOSITE_DIALOGUE_RECORDS),
            ("T00604", "T00893"),
        )
        self.assertEqual(CONTINUATION_IDS, frozenset({"T00605", "T00894"}))

    def test_dynamic_label_controls_are_exact(self) -> None:
        self.assertEqual(BY_OWNER_ID["T00604"].control, bytes.fromhex("3D 00 06"))
        self.assertEqual(BY_OWNER_ID["T00893"].control, bytes.fromhex("3D 00 1B"))

    def test_physical_offsets_are_the_authenticated_markers(self) -> None:
        self.assertEqual(BY_OWNER_ID["T00604"].marker_offset, 0x00177DA8)
        self.assertEqual(BY_OWNER_ID["T00893"].marker_offset, 0x00CFA1C1)


if __name__ == "__main__":
    unittest.main()
