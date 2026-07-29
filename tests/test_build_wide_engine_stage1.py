"""Test the deterministic Stage 1 disc-build plan without copying a disc."""

from __future__ import annotations

import unittest

from build_wide_engine_stage1 import (
    TEST_FOOTPRINT,
    TEST_OFFSET,
    TEST_TEXT,
    stage1_payload_patches,
)
from wide_runtime_stage1 import WIDE_END, WIDE_START


class Stage1BuildPlanTests(unittest.TestCase):
    """Keep the tester-visible field and runtime plan source-guarded."""

    def test_stage1_patch_plan_has_runtime_ranges_and_one_field(
        self,
    ) -> None:
        """Keep the build scope narrow, deterministic, and same-size."""

        patches = stage1_payload_patches()
        self.assertEqual(len(patches), 4)
        self.assertEqual(patches[-1].offset, TEST_OFFSET)
        self.assertEqual(len(patches[-1].replacement), TEST_FOOTPRINT)
        self.assertEqual(patches[-1].replacement[0], WIDE_START)
        self.assertEqual(patches[-1].replacement[-1], WIDE_END)
        self.assertEqual(
            patches[-1].replacement[2:-1],
            TEST_TEXT.encode("ascii"),
        )
        self.assertTrue(all(
            len(patch.expected) == len(patch.replacement) for patch in patches
        ))


if __name__ == "__main__":
    unittest.main()
