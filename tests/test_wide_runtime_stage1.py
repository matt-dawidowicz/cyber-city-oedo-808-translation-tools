"""Test the intentionally narrow first runtime milestone."""

from __future__ import annotations

import unittest

from wide_runtime_stage1 import (
    MISSION0_CODE_CAVE_SIZE,
    MISSION0_GLYPH_HOOK_CPU,
    MISSION0_PARSER_HOOK_CPU,
    WIDE_END,
    WIDE_START,
    WIDE_TAG,
    build_stage1_runtime_patches,
    encode_stage1_field,
)


class WideRuntimeStage1Tests(unittest.TestCase):
    """Keep the runtime test field and code guards deterministic."""

    def test_exact_footprint_stream_uses_literal_ascii_markers(self) -> None:
        """End escape mode immediately before the original next byte."""

        stream = encode_stage1_field("WIDE ENGINE ESCAPE TEST X", 28)
        self.assertEqual(stream[0], WIDE_START)
        self.assertEqual(stream[-1], WIDE_END)
        self.assertEqual(stream[1], WIDE_TAG)
        self.assertEqual(stream[2:-1], b"WIDE ENGINE ESCAPE TEST X")

    def test_tag_distinguishes_the_observed_ordinary_ff_fe_pair(self) -> None:
        """Reserve the escape path for FF 00, not the prologue's FF FE data."""

        self.assertNotEqual(bytes((WIDE_START, WIDE_END))[1], WIDE_TAG)

    def test_rejects_padding_and_unimplemented_stage1_glyphs(self) -> None:
        """Avoid speculative filler, punctuation, lowercase, and newlines."""

        invalid_cases = (
            ("WIDE TEST", 28),
            ("WIDE TEST!", 12),
            ("Wide Test", 11),
            ("WIDE\nTEST", 11),
        )
        for text, footprint in invalid_cases:
            with self.subTest(text=text, footprint=footprint):
                with self.assertRaises(ValueError):
                    encode_stage1_field(text, footprint)

    def test_runtime_patches_preserve_guards_and_cave_boundary(
        self,
    ) -> None:
        """Keep every hook same-size and the cave exactly source-guarded."""

        patches = build_stage1_runtime_patches()
        self.assertEqual([patch.cpu_address for patch in patches], [
            MISSION0_PARSER_HOOK_CPU,
            MISSION0_GLYPH_HOOK_CPU,
            0x9F1B,
        ])
        self.assertTrue(
            all(len(p.expected) == len(p.replacement) for p in patches)
        )
        self.assertEqual(len(patches[-1].replacement), MISSION0_CODE_CAVE_SIZE)
        self.assertEqual(patches[0].replacement[0], 0x20)
        self.assertEqual(patches[1].replacement[0], 0x20)


if __name__ == "__main__":
    unittest.main()
