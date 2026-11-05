"""Regression safeguards for ADPCM caves rejected by live emulator evidence."""

from __future__ import annotations

import unittest

from cyber_oedo.runtime.adpcm_code_cave_ownership import (
    KNOWN_REJECTED_M0B_WINDOWS,
    assess_adpcm_code_cave,
    require_release_certified_adpcm_cave,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    QUARANTINED_ADPCM_PROFILES,
    build_intro_smoke_polish_patches,
)


class AdpcmCodeCaveOwnershipTests(unittest.TestCase):
    def test_evidence_grounded_windows_are_exact(self) -> None:
        self.assertEqual(
            tuple((w.overlay, w.start_cpu, w.end_cpu_exclusive)
                  for w in KNOWN_REJECTED_M0B_WINDOWS),
            (
                ("mission0b", 0x4C93, 0x4CFA),
                ("mission0b", 0x4CFA, 0x4D61),
                ("mission0b", 0x8F51, 0x8FB0),
            ),
        )

    def test_legacy_audio_collides_with_repaired_portrait(self) -> None:
        result = assess_adpcm_code_cave(
            overlay="mission0b", start_cpu=0x4CFA, code_length=95
        )
        self.assertTrue(result.known_rejected)
        self.assertIn("portrait", result.rejected_regions[0].reason)
        self.assertFalse(result.release_eligible)

    def test_old_portrait_area_was_overwritten(self) -> None:
        result = assess_adpcm_code_cave(
            overlay="mission0b", start_cpu=0x4C93, code_length=103
        )
        self.assertTrue(result.known_rejected)
        self.assertGreaterEqual(len(result.rejected_regions), 1)

    def test_module_bss_tail_is_live_code_not_a_cave(self) -> None:
        result = assess_adpcm_code_cave(
            overlay="mission0b", start_cpu=0x8F51, code_length=95
        )
        self.assertTrue(result.known_rejected)
        self.assertIn("exec", result.rejected_regions[0].reason)
        self.assertFalse(result.runtime_ownership_certified)
        self.assertFalse(result.multi_mission_certified)
        with self.assertRaisesRegex(ValueError, "known unsafe ADPCM code cave"):
            require_release_certified_adpcm_cave(
                overlay="mission0b", start_cpu=0x8F51, code_length=95
            )

    def test_partial_overlap_cannot_avoid_rejection(self) -> None:
        self.assertTrue(
            assess_adpcm_code_cave(
                overlay="mission0b", start_cpu=0x8FAF, code_length=2
            ).known_rejected
        )

    def test_unknown_is_not_equivalent_to_certified(self) -> None:
        result = assess_adpcm_code_cave(
            overlay="mission0b", start_cpu=0x7000, code_length=95
        )
        self.assertFalse(result.known_rejected)
        self.assertFalse(result.release_eligible)
        with self.assertRaisesRegex(ValueError, "executable region unverified"):
            require_release_certified_adpcm_cave(
                overlay="mission0b", start_cpu=0x7000, code_length=95
            )

    def test_overlay_scope_is_preserved_not_conflated(self) -> None:
        result = assess_adpcm_code_cave(
            overlay="mission1", start_cpu=0x8F51, code_length=95
        )
        self.assertFalse(result.known_rejected)
        self.assertFalse(result.multi_mission_certified)

    def test_invalid_address_spans_fail_closed(self) -> None:
        for start, length in ((-1, 95), (0xFFFF, 2), (0x8000, 0)):
            with self.subTest(start=start, length=length):
                with self.assertRaisesRegex(ValueError, "16-bit CPU address"):
                    assess_adpcm_code_cave(
                        overlay="mission0b", start_cpu=start, code_length=length
                    )

    def test_existing_adpcm_profiles_stay_unavailable(self) -> None:
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
