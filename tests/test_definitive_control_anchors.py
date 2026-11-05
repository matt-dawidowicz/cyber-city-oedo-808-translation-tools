from __future__ import annotations

import unittest
from collections import Counter

from cyber_oedo.text.definitive_control_anchors import (
    DEFINITIVE_CONTROL_ANCHORS,
    DEFINITIVE_CONTROL_BYTES,
    DEFINITIVE_CONTROL_METHODS,
    LOCKED_CONTROL_ANCHOR_COUNT,
)


class DefinitiveControlAnchorTests(unittest.TestCase):
    def test_all_79_reviewed_rows_are_frozen(self) -> None:
        self.assertEqual(LOCKED_CONTROL_ANCHOR_COUNT, 79)
        self.assertEqual(len(DEFINITIVE_CONTROL_ANCHORS), 79)
        self.assertEqual(set(DEFINITIVE_CONTROL_ANCHORS), set(DEFINITIVE_CONTROL_METHODS))
        self.assertEqual(set(DEFINITIVE_CONTROL_ANCHORS), set(DEFINITIVE_CONTROL_BYTES))

    def test_reviewed_method_distribution_matches_workbook(self) -> None:
        self.assertEqual(
            Counter(DEFINITIVE_CONTROL_METHODS.values()),
            Counter(
                {
                    "editorial_english_phrase_pacing": 73,
                    "editorial_semantic_anchor": 4,
                    "composite_record_dynamic_label": 2,
                }
            ),
        )

    def test_fragment_count_is_control_count_plus_one(self) -> None:
        for entry_id, fragments in DEFINITIVE_CONTROL_ANCHORS.items():
            controls = DEFINITIVE_CONTROL_BYTES[entry_id].split(" | ")
            self.assertEqual(
                len(fragments),
                len(controls) + 1,
                entry_id,
            )

    def test_composite_anchors_are_present(self) -> None:
        self.assertEqual(
            DEFINITIVE_CONTROL_ANCHORS["T00604"],
            ("I waited a while...", "‘You're awfully quiet.’"),
        )
        self.assertEqual(
            DEFINITIVE_CONTROL_ANCHORS["T00893"],
            ("I waited a while.", "‘What's wrong? The rest area is over there.’"),
        )


if __name__ == "__main__":
    unittest.main()
