"""Fail-closed structural unit tests for the unverified M0B tail prototype.

These tests do not certify BSS ownership, sound output, or later missions.
"""

from __future__ import annotations

import unittest

from cyber_oedo.runtime.shared_module_adpcm_candidate import (
    ADPCM_TAIL_CODE,
    EXTENDED_MODULE_BYTES,
    LOADER_LENGTH_LOW_BYTE_OFFSET,
    SOURCE_LOADER_BYTE_COUNT,
    TAIL_CODE_CPU,
    TAIL_CODE_SOURCE_OFFSET,
    build_unverified_dialogue_tail_candidate,
)
from cyber_oedo.runtime.card_ram_adpcm_cache import ADPCM_CALL_OFFSET
from cyber_oedo.runtime.card_ram_portrait_cache import PORTRAIT_CACHE_CAVE_OFFSET
from cyber_oedo.runtime.dialogue_load_architecture import (
    DIALOGUE_MODULE_LBA,
    payload_offset_for_lba,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    QUARANTINED_ADPCM_PROFILES,
    build_intro_smoke_polish_patches,
)


class SharedModuleAdpcmCandidateTests(unittest.TestCase):
    def test_unsafe_acknowledgment_is_mandatory(self) -> None:
        with self.assertRaisesRegex(ValueError, "unverified dialogue-module BSS"):
            build_unverified_dialogue_tail_candidate()

    def test_distinct_source_patch_ranges(self) -> None:
        candidate = build_unverified_dialogue_tail_candidate(unsafe_research=True)
        self.assertEqual(len(candidate.patches), 5)
        self.assertFalse(candidate.runtime_ownership_certified)
        self.assertFalse(candidate.audio_fidelity_certified)
        self.assertFalse(candidate.cross_overlay_certified)
        self.assertFalse(candidate.release_enabled)

        offsets = [patch.offset for patch in candidate.patches]
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertEqual(offsets, sorted(offsets))
        for left, right in zip(candidate.patches, candidate.patches[1:]):
            self.assertLessEqual(left.end_offset, right.offset)

        self.assertIn(ADPCM_CALL_OFFSET, offsets)
        self.assertIn(PORTRAIT_CACHE_CAVE_OFFSET, offsets)
        self.assertIn(TAIL_CODE_SOURCE_OFFSET, offsets)
        self.assertIn(LOADER_LENGTH_LOW_BYTE_OFFSET, offsets)

    def test_exact_module_tail_source_guard_and_bounds(self) -> None:
        candidate = build_unverified_dialogue_tail_candidate(unsafe_research=True)
        cave = next(p for p in candidate.patches if p.offset == TAIL_CODE_SOURCE_OFFSET)
        self.assertEqual(TAIL_CODE_CPU, 0x8F51)
        self.assertEqual(cave.offset, payload_offset_for_lba(DIALOGUE_MODULE_LBA) + 0x0F51)
        self.assertEqual(len(ADPCM_TAIL_CODE), 95)
        self.assertEqual(cave.expected, bytes(95))
        self.assertEqual(cave.replacement, ADPCM_TAIL_CODE)
        self.assertEqual(cave.replacement[:8], bytes.fromhex("43 20 48 43 40 48 A9 6B"))
        self.assertEqual(TAIL_CODE_CPU + len(cave.replacement), 0x8FB0)
        self.assertLess(0x8FB0, 0x8FDD)

    def test_source_loader_length_guard(self) -> None:
        candidate = build_unverified_dialogue_tail_candidate(unsafe_research=True)
        length_patch = next(
            p for p in candidate.patches if p.offset == LOADER_LENGTH_LOW_BYTE_OFFSET
        )
        self.assertEqual(SOURCE_LOADER_BYTE_COUNT, 0x0F51)
        self.assertEqual(EXTENDED_MODULE_BYTES, 0x0FB0)
        self.assertEqual(length_patch.expected, b"\x51")
        self.assertEqual(length_patch.replacement, b"\xB0")

    def test_wrong_authenticated_source_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            build_unverified_dialogue_tail_candidate(
                unsafe_research=True, authenticated_payload=b"not an original track"
            )

    def test_existing_builder_profiles_remain_quarantined(self) -> None:
        self.assertEqual(
            QUARANTINED_ADPCM_PROFILES,
            frozenset({"adpcm", "portrait-adpcm", "all-seven"}),
        )
        for profile in QUARANTINED_ADPCM_PROFILES:
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "cross-overlay ADPCM"):
                    build_intro_smoke_polish_patches(profile)


if __name__ == "__main__":
    unittest.main()
