"""Synthetic composition checks, not Mesen gameplay or release certification.

The historical seven-patch performance profile has known Mesen regressions;
exercise it only with explicit unsafe opt-in and keep normal execution inert.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from cyber_oedo.runtime.combined_fast_load_benchmark import (
    build_combined_bar_benchmark,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    compose_polish_patches,
    build_intro_smoke_polish_patches,
    CACHE_BANKS,
    ENGLISH_POOL_BANKS,
    PERFORMANCE_EXPERIMENTS, QUARANTINED_ADPCM_PROFILES,
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
    def test_default_enables_no_experimental_performance_patches(self):
        self.assertEqual(build_intro_smoke_polish_patches(), ())
        items, runtime, atlas = compose_polish_patches(SparseAuthenticatedSource())
        self.assertEqual(items, ())
        self.assertIsNone(runtime)
        self.assertIsNone(atlas)

    def test_performance_experiments_require_unsafe_acknowledgment(self):
        for profile in PERFORMANCE_EXPERIMENTS:
            if profile == "none":
                continue
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError,
                                            "--acknowledge-unsafe-performance"):
                    compose_polish_patches(
                        SparseAuthenticatedSource(),
                        performance_experiment=profile,
                    )

    def test_shared_dialogue_adpcm_hook_is_quarantined(self):
        # The common $1425 module is also used while Mission-0-B's
        # outer-overlay cave $4CFA is not present. Source-guarded writes
        # do not protect a mismapped cross-bank JSR at runtime.
        for profile in QUARANTINED_ADPCM_PROFILES:
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "cross-overlay ADPCM"):
                    build_intro_smoke_polish_patches(profile)
                with self.assertRaisesRegex(ValueError, "cross-overlay ADPCM"):
                    compose_polish_patches(
                        SparseAuthenticatedSource(),
                        performance_experiment=profile,
                        acknowledge_unsafe_performance=True,
                    )

    def test_narrow_experiments_remain_available_but_acknowledged(self):
        for profile, size in (("portrait", 2), ("selective-restore", 3)):
            with self.subTest(profile=profile):
                items, runtime, atlas = compose_polish_patches(
                    SparseAuthenticatedSource(),
                    performance_experiment=profile,
                    acknowledge_unsafe_performance=True,
                )
                self.assertEqual(len(items), size)
                self.assertIsNone(runtime)
                self.assertIsNone(atlas)

    def test_english_pilot_defaults_to_no_performance_patches(self):
        original = SparseAuthenticatedSource(include_english=True)
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            items, runtime, atlas = compose_polish_patches(
                original, english_pilot=True
            )
        self.assertEqual(len(items), 10)
        self.assertIsNotNone(runtime)
        self.assertIsNotNone(atlas)
        performance_patches = (
            build_intro_smoke_polish_patches("portrait") +
            build_intro_smoke_polish_patches("selective-restore")
        )
        self.assertTrue(all(
            left.end_offset <= right.offset or right.end_offset <= left.offset
            for left in items for right in performance_patches
        ))

    def test_english_pilot_composes_with_nonquarantined_experiments(self):
        for profile, extra in (("portrait", 2), ("selective-restore", 3)):
            with self.subTest(profile=profile):
                original = SparseAuthenticatedSource(include_english=True)
                with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
                    items, runtime, atlas = compose_polish_patches(
                        original, english_pilot=True,
                        performance_experiment=profile,
                        acknowledge_unsafe_performance=True,
                    )
                self.assertEqual(len(items), 10 + extra)
                self.assertIsNotNone(runtime)
                self.assertIsNotNone(atlas)
                self.assertEqual(CACHE_BANKS, "$68-$6C")
                self.assertEqual(ENGLISH_POOL_BANKS, "$7C-$7F")
                self.assertTrue(all(left.end_offset <= right.offset
                                    for left, right in zip(items, items[1:])))

    def test_corrupt_core_source_refused(self):
        for item in (build_intro_smoke_polish_patches("portrait") +
                     build_intro_smoke_polish_patches("selective-restore")):
            with self.subTest(label=item.label, offset=item.offset):
                original = SparseAuthenticatedSource()
                corrupt = bytes((item.expected[0] ^ 0xFF,)) + item.expected[1:]
                original.slices[(item.offset, len(item.expected))] = corrupt
                with self.assertRaisesRegex(ValueError, "signature mismatch"):
                    compose_polish_patches(
                        original, performance_experiment=(
                            "portrait" if "portrait" in item.label.lower()
                            else "selective-restore"
                        ),
                        acknowledge_unsafe_performance=True,
                    )

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
