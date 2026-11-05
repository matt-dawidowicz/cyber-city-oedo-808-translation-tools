"""Fail-closed guardrails for shared Mission-0 performance-cache code caves.

This is structural evidence, not proof of any overlay's live ownership.
"""

from __future__ import annotations

import unittest

from cyber_oedo.runtime.card_ram_adpcm_cache import (
    ADPCM_CACHE_CAVE_OFFSET,
    ADPCM_CACHE_CAVE_REPLACEMENT,
    build_speaker_adpcm_cache_benchmark,
)
from cyber_oedo.runtime.card_ram_portrait_cache import (
    PORTRAIT_CACHE_CAVE_OFFSET,
    PORTRAIT_CACHE_CAVE_REPLACEMENT,
    build_portrait_cache_benchmark,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    QUARANTINED_ADPCM_PROFILES,
    build_intro_smoke_polish_patches,
)


class CaveOwnershipTests(unittest.TestCase):
    """Prevent combining physically overlapping cache implementations."""

    def test_portrait_and_archived_adpcm_caves_physically_collide(self) -> None:
        """Keep the two exact source-derived cave extents visible in CI."""
        portrait = (
            PORTRAIT_CACHE_CAVE_OFFSET,
            PORTRAIT_CACHE_CAVE_OFFSET + len(PORTRAIT_CACHE_CAVE_REPLACEMENT),
        )
        adpcm = (
            ADPCM_CACHE_CAVE_OFFSET,
            ADPCM_CACHE_CAVE_OFFSET + len(ADPCM_CACHE_CAVE_REPLACEMENT),
        )
        self.assertEqual(portrait, (0x001364FA, 0x00136561))
        self.assertEqual(adpcm, (0x001364FA, 0x00136559))
        self.assertLess(max(portrait[0], adpcm[0]), min(portrait[1], adpcm[1]))

    def test_benchmarks_are_source_guarded_but_not_composable(self) -> None:
        """Reject the overlap even though each independent patch has a guard."""
        portrait = build_portrait_cache_benchmark().patches
        adpcm = build_speaker_adpcm_cache_benchmark().patches
        cave_a = next(p for p in portrait if p.offset == PORTRAIT_CACHE_CAVE_OFFSET)
        cave_b = next(p for p in adpcm if p.offset == ADPCM_CACHE_CAVE_OFFSET)
        self.assertEqual(cave_a.expected, bytes(len(cave_a.expected)))
        self.assertEqual(cave_b.expected, bytes(len(cave_b.expected)))
        self.assertLess(cave_a.offset, cave_b.end_offset)
        self.assertLess(cave_b.offset, cave_a.end_offset)

    def test_unsafe_acknowledgment_cannot_restore_legacy_adpcm_profiles(self) -> None:
        """Do not remove quarantine based on a portrait-only watcher replay."""
        self.assertEqual(
            QUARANTINED_ADPCM_PROFILES,
            frozenset({'adpcm', 'portrait-adpcm', 'all-seven'}),
        )
        for profile in QUARANTINED_ADPCM_PROFILES:
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, 'cross-overlay ADPCM'):
                    build_intro_smoke_polish_patches(profile)


if __name__ == '__main__':
    unittest.main()
