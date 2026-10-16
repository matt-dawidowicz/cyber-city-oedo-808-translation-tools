"""Regress engine polish composition without requiring any copyrighted media."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from cyber_oedo.runtime.combined_fast_load_benchmark import (
    build_combined_bar_benchmark,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    compose_polish_patches,
    CACHE_BANKS,
    ENGLISH_POOL_BANKS,
)
from cyber_oedo.runtime.mission0_pool_pilot import (
    BARTENDER_MARKER_OFFSET, BARTENDER_SOURCE_TEXT,
    M0B_SOURCE_BASE, M0B_TABLE_LOADER_CPU, M0B_TABLE_LOADER_EXPECTED,
    POOL_START_RELATIVE_SECTOR, SOURCE_REDIRECT_BYTES, _make_runtime,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.oedo_pixel_font import authored_atlas


class SparseAuthenticatedSource:
    """Models guarded original slices; no original game bytes are in tests."""

    def __init__(self, include_english: bool = False):
        self.slices: dict[tuple[int, int], bytes] = {}
        for item in build_combined_bar_benchmark().patches:
            self.slices[(item.offset, len(item.expected))] = item.expected
        if include_english:
            glyphs = EnglishGlyphTable.from_texts(("Bartender: Welcome.", " ?"))
            atlas = authored_atlas(glyphs.characters)
            runtime = _make_runtime(glyphs, atlas)
            b = M0B_SOURCE_BASE
            expected = bytes(min(len(runtime.font), 0x400))
            expected += bytes((0xE5,)) * max(len(runtime.font) - 0x400, 0)
            self.slices.update({
                (b + M0B_TABLE_LOADER_CPU, 8): M0B_TABLE_LOADER_EXPECTED,
                (b + 0x9543, 3): bytes.fromhex("20 11 9F"),
                (b + 0x95D4, 3): bytes.fromhex("C9 80 F0"),
                (b + 0x9F11, 3): bytes.fromhex("B2 7F 60"),
                (b + 0x9F14, 6): bytes.fromhex("E6 7F D0 02 E6 80"),
                (b + 0x56C0, 3): bytes.fromhex("20 60 E0"),
                (b + 0xA400, len(runtime.font)): expected,
                (b + 0xAC00, len(runtime.full_code)):
                    bytes((0xE5,)) * len(runtime.full_code),
                (POOL_START_RELATIVE_SECTOR * 2048, 0x8000): bytes(0x8000),
                (BARTENDER_MARKER_OFFSET + 2, SOURCE_REDIRECT_BYTES):
                    BARTENDER_SOURCE_TEXT.encode("shift_jis")[:SOURCE_REDIRECT_BYTES],
            })

    def __getitem__(self, key: slice) -> bytes:
        if not isinstance(key, slice):
            raise TypeError("test source only supports guarded slices")
        try:
            return self.slices[(key.start, key.stop - key.start)]
        except KeyError as error:
            raise AssertionError(
                f"attempted to read unguarded source region: {key}"
            ) from error


class EnginePolishCompositionTests(unittest.TestCase):
    def test_core_uses_only_existing_nonaggressive_safe_fallback_edits(self):
        original = SparseAuthenticatedSource()
        items, runtime, atlas = compose_polish_patches(original)
        self.assertEqual(len(items), 7)
        self.assertIsNone(runtime)
        self.assertIsNone(atlas)
        self.assertTrue(all(original[p.offset:p.end_offset] == p.expected
                            for p in items))
        labels = " ".join(p.label.lower() for p in items)
        for prohibited in (
            "hard audio", "fade", "120-frame", "speaker cache selector",
            "resident-module", "jmp entrypoints",
        ):
            self.assertNotIn(prohibited, labels)

    def test_english_pilot_can_be_composed_with_fastload_no_overlap(self):
        original = SparseAuthenticatedSource(include_english=True)
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            items, runtime, atlas = compose_polish_patches(
                original, english_pilot=True
            )
        self.assertEqual(len(items), 17)
        self.assertIsNotNone(runtime)
        self.assertIsNotNone(atlas)
        self.assertEqual(CACHE_BANKS, "$68-$6C")
        self.assertEqual(ENGLISH_POOL_BANKS, "$7C-$7F")
        self.assertTrue(all(left.end_offset <= right.offset
                            for left, right in zip(items, items[1:])))

    def test_corrupt_core_source_refused(self):
        original = SparseAuthenticatedSource()
        first = build_combined_bar_benchmark().patches[0]
        original.slices[(first.offset, len(first.expected))] = bytes(
            len(first.expected)
        )
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            compose_polish_patches(original)

    def test_no_diagnostic_text_without_english(self):
        with self.assertRaisesRegex(ValueError, "requires --english-pilot"):
            compose_polish_patches(SparseAuthenticatedSource(),
                                   diagnostic_intro=True)

    def test_bad_character_is_rejected_not_silently_replaced(self):
        original = SparseAuthenticatedSource(include_english=True)
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            with self.assertRaisesRegex(ValueError, "unsupported"):
                compose_polish_patches(
                    original, english_pilot=True, english="Café"
                )


if __name__ == "__main__":
    unittest.main()
