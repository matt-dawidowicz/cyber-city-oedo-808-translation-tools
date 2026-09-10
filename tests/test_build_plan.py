"""Regression tests for decomposed human-test build planning."""

from __future__ import annotations

import unittest

from cyber_oedo.build import human_test
from cyber_oedo.build.plan import build_profile_plan
from cyber_oedo.build.recipe import prepare_build_recipe
from cyber_oedo.build.profiles import mission0_stock as profile


class BuildPlanTests(unittest.TestCase):
    """Keep the hash-only plan deterministic and profile-equivalent."""

    def test_original_plan_is_deterministic(self) -> None:
        """Produce the same canonical plan identity on repeated builds."""

        first = human_test.planned_profile("original")
        second = human_test.planned_profile("original")
        self.assertEqual(first, second)
        self.assertEqual(first.sha256(), second.sha256())

    def test_refactor_preserves_reviewed_plan_identities(self) -> None:
        """Pin both title variants across behavior-preserving refactors."""

        self.assertEqual(
            build_profile_plan("original").sha256(),
            "7372c5ee7dc54d30bf2545a5ca9eaa8ad9231e03ecf2cb3faaf723d0cbad3de5",
        )
        self.assertEqual(
            build_profile_plan("clean").sha256(),
            "3255c65bbd3dd8ec37daf05d315894ad3a1b7af5815228bcf9034b046367b4bb",
        )

    def test_clean_recipe_is_hash_only_without_source_image(self) -> None:
        """Require source bytes before materializing guarded clean-title edits."""

        recipe = prepare_build_recipe("clean")
        with self.assertRaisesRegex(ValueError, "hash-only"):
            recipe.payload_patches()

    def test_clean_plan_adds_exactly_two_title_entries(self) -> None:
        """Represent only the isolated palette and title additions."""

        original = build_profile_plan("original")
        clean = build_profile_plan("clean")
        self.assertEqual(len(clean.entries), len(original.entries) + 2)
        self.assertEqual(
            [entry.category for entry in clean.entries[-2:]],
            ["title", "title"],
        )

    def test_plan_matches_independent_sector_footprint(self) -> None:
        """Keep plan spans equal to the profile's reviewed footprint."""

        for mode in profile.TITLE_SCREEN_MODES:
            plan = human_test.planned_profile(mode)
            self.assertEqual(
                plan.guarded_relative_sectors,
                profile.profile_relative_sectors(mode),
            )

    def test_plan_does_not_serialize_source_bytes(self) -> None:
        """Expose source identities as hashes rather than copyrighted bytes."""

        row = human_test.planned_profile("clean").to_dict()["entries"][0]
        self.assertIn("expected_sha256", row)
        self.assertIn("replacement_sha256", row)
        self.assertNotIn("expected_hex", row)
        self.assertNotIn("replacement_hex", row)

    def test_package_builder_is_the_public_build_facade(self) -> None:
        """Expose the build pipeline through the package rather than a shim."""

        from cyber_oedo.build.pipeline import build_human_test_disc

        self.assertIs(
            human_test.build_human_test_disc,
            build_human_test_disc,
        )


if __name__ == "__main__":
    unittest.main()
