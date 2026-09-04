"""Synthetic regression tests for retained reverse-engineering primitives."""

from __future__ import annotations

import unittest

from cyber_oedo.analysis.analyze_text_slots import looks_like_resource_name
from cyber_oedo.analysis.scan_track import entropy, zero_runs
from cyber_oedo.disc.game_layout import SECTOR_SIZE, bank_for_offset
from cyber_oedo.graphics.pce_graphics import decode_tile, encode_tile
from cyber_oedo.text.extract_auxiliary_text import merge_ranges
from cyber_oedo.text.extract_dialogue import parse_record


class CoreTests(unittest.TestCase):
    """Protect verified low-level behavior across the restart."""

    def test_bank_boundaries_are_half_open(self) -> None:
        """Assign bytes at a mission-bank boundary deterministically."""

        boundary = 5376 * SECTOR_SIZE
        self.assertEqual(bank_for_offset(boundary - 1), "MISSION_0")
        self.assertEqual(bank_for_offset(boundary), "MISSION_1")

    def test_dialogue_controls_remain_distinct_from_text(self) -> None:
        """Preserve low byte values as opaque control tags."""

        data = "猫".encode("shift_jis") + b"\x40" + "犬".encode("shift_jis")
        parsed = parse_record(data + b"\x00", 0)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("".join(parsed.text_only), "猫犬")
        self.assertEqual("".join(parsed.tokens), "猫<$40>犬")
        self.assertEqual(parsed.controls, (0x40,))

    def test_tile_codec_round_trips(self) -> None:
        """Round-trip all four PC Engine tile bitplanes."""

        pixels = [(index * 7) % 16 for index in range(64)]
        self.assertEqual(decode_tile(encode_tile(pixels)), pixels)

    def test_range_merging_coalesces_adjacent_ranges(self) -> None:
        """Normalize overlapping and touching dialogue intervals."""

        self.assertEqual(
            merge_ranges([(20, 30), (0, 10), (8, 20), (40, 40)]),
            [(0, 30)],
        )

    def test_resource_name_filter_rejects_fill(self) -> None:
        """Reject repeated fill while retaining plausible identifiers."""

        self.assertTrue(looks_like_resource_name("BARTEN1"))
        self.assertFalse(looks_like_resource_name("UUUUUUUU"))

    def test_structural_helpers(self) -> None:
        """Keep entropy and zero-run helpers stable on trivial input."""

        self.assertEqual(entropy(bytes(32)), 0.0)
        self.assertEqual(zero_runs([True, True, False, True]), [(0, 2), (3, 4)])


if __name__ == "__main__":
    unittest.main()
