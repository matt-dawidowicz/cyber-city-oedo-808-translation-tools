"""Regression tests for the stock-renderer build profile."""

from __future__ import annotations

import hashlib
import pathlib
import unittest

from cyber_oedo.build import engine
from cyber_oedo.graphics.title_screen import (
    BACKGROUND_INDEX,
    TITLE_FIRST_VISIBLE_INDEX,
    TITLE_PALETTE_BYTES,
    TITLE_PALETTE_COLORS,
    TITLE_PALETTE_FRAMES,
    TITLE_PALETTE_LEVELS,
    TITLE_SUBTITLE,
    build_clean_title_asset,
    build_clean_title_pixels,
    build_grayscale_title_palette_cycle,
    encode_title_pixels,
    title_palette_index,
)


class HumanTestProfileTests(unittest.TestCase):
    """Protect the known-good stock-renderer profile contract."""

    def test_text_patch_count_and_size_contract(self) -> None:
        """Keep all existing profile text replacements same-size."""

        self.assertEqual(len(engine.HUMAN_TEST_PATCHES), 271)
        for text_patch in engine.HUMAN_TEST_PATCHES:
            patch = text_patch.to_payload_patch()
            self.assertEqual(len(patch.expected), len(patch.replacement))

    def test_profile_has_no_dialogue_renderer_code_patch(self) -> None:
        """Keep the failed renderer experiment out of the stock profile."""

        self.assertEqual(engine.MISSION0_RENDERER_PATCHES, ())
        self.assertEqual(
            len(engine.HUMAN_TEST_BINARY_PATCHES),
            len(engine.OPENING_PROFILE_LAYOUT_PATCHES)
            + len(engine.INFORMATION_SCREEN_LAYOUT_PATCHES),
        )

    def test_opening_profiles_cover_both_banks(self) -> None:
        """Keep both copies of all seven opening dossiers translated."""

        self.assertEqual(len(engine.OPENING_PROFILE_FIELDS), 80)
        self.assertEqual(len(engine.OPENING_PROFILE_TEXT_PATCHES), 160)
        self.assertEqual(len(engine.OPENING_PROFILE_LAYOUT_PATCHES), 46)
        self.assertEqual(
            {field.profile for field in engine.OPENING_PROFILE_FIELDS},
            {
                "chris",
                "kenichi",
                "jun",
                "manny",
                "sanemaro",
                "benten",
                "gogul",
            },
        )

    def test_media_mix_rows_are_nonoverlapping(self) -> None:
        """Keep visible 16-pixel lines separated by two tile rows."""

        self.assertEqual(len(engine.INFORMATION_SCREEN_LINES), 43)
        self.assertEqual(len(engine.INFORMATION_SCREEN_LAYOUT_PATCHES), 34)
        for screen in {"video", "novel", "music"}:
            rows = [
                line.display_row
                for line in engine.INFORMATION_SCREEN_LINES
                if line.screen == screen and line.english
            ]
            self.assertEqual(len(rows), len(set(rows)))
            self.assertTrue(
                all(b - a >= 2 for a, b in zip(rows, rows[1:]))
            )

    def test_profile_sector_footprints_remain_stable(self) -> None:
        """Keep original/clean title variants on reviewed sectors."""

        original = set(engine.profile_relative_sectors("original"))
        clean = set(engine.profile_relative_sectors("clean"))
        self.assertEqual(len(original), 21)
        self.assertEqual(len(clean), 37)
        self.assertTrue(original < clean)

    def test_fullwidth_encoder_rejects_control_characters(self) -> None:
        """Keep replacement glyph bytes out of the low-byte control range."""

        self.assertEqual(engine.ascii_to_fullwidth("A 1!"), "Ａ　１！")
        self.assertEqual(engine.ascii_to_fullwidth("A-B'S"), "Ａ−Ｂ’Ｓ")
        with self.assertRaises(ValueError):
            engine.ascii_to_fullwidth("line\nbreak")

    def test_word_wrap_is_stable(self) -> None:
        """Keep the confirmed 11-cell stock-renderer wrapping behavior."""

        wrapped = engine.wrap_ascii_text(
            "I hunt crooks and turn them in.",
            engine.PROLOGUE_WRAP_WIDTH,
        )
        self.assertEqual(
            [wrapped[:11], wrapped[11:22], wrapped[22:33], wrapped[33:]],
            ["I hunt     ", "crooks and ", "turn them  ", "in."],
        )


class TitleScreenTests(unittest.TestCase):
    """Protect the optional generated title asset."""

    def test_generated_asset_identity_is_stable(self) -> None:
        """Keep the reviewed 256-by-240 title replacement byte-exact."""

        pixels = build_clean_title_pixels()
        asset = build_clean_title_asset()
        self.assertEqual(len(asset), engine.TITLE_ASSET_BYTES)
        self.assertEqual(
            hashlib.sha256(asset).hexdigest(),
            "f8e91ad827040796ea63a80541e06f71"
            "159ca18121b10ab5128347ad6206e8f1",
        )
        self.assertEqual(TITLE_SUBTITLE, "ATTRIBUTE OF THE BEAST")
        self.assertEqual(
            set(pixels),
            {BACKGROUND_INDEX, *range(TITLE_FIRST_VISIBLE_INDEX, 16)},
        )
        with self.assertRaises(ValueError):
            encode_title_pixels(pixels[:-1])

    def test_title_palette_cycle_is_stable(self) -> None:
        """Keep all seven title frames on the approved grayscale palette."""

        palette = build_grayscale_title_palette_cycle()
        self.assertEqual(len(palette), TITLE_PALETTE_BYTES)
        frame_bytes = TITLE_PALETTE_COLORS * 2
        frames = [
            palette[offset:offset + frame_bytes]
            for offset in range(0, len(palette), frame_bytes)
        ]
        self.assertEqual(len(frames), TITLE_PALETTE_FRAMES)
        self.assertTrue(all(frame == frames[0] for frame in frames))
        words = [
            int.from_bytes(frames[0][offset:offset + 2], "little")
            for offset in range(0, frame_bytes, 2)
        ]
        self.assertEqual(words, [level * 0x49 for level in TITLE_PALETTE_LEVELS])

    def test_original_mode_does_not_read_title_source(self) -> None:
        """Keep title opt-out independent of an IMG read."""

        nonexistent = pathlib.Path("source-image-is-not-needed.img")
        self.assertEqual(
            engine.optional_title_screen_patches(nonexistent, "original"),
            (),
        )
        self.assertEqual(title_palette_index(0), BACKGROUND_INDEX)


if __name__ == "__main__":
    unittest.main()
