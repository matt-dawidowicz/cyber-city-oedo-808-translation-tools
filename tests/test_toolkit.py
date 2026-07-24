"""Regression tests for documented binary-format behavior.

These tests use synthetic bytes.  They are fast enough to run after every code
edit and do not require redistributing or copying the game image.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest


# Allow ``python -m unittest discover -s tests`` from the toolkit directory
# without turning the scripts into an installed Python package.
TOOLKIT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT_DIR))

from analyze_text_slots import looks_like_resource_name  # noqa: E402
from extract_auxiliary_text import merge_ranges  # noqa: E402
from extract_dialogue import parse_record  # noqa: E402
from extract_track2_mode1 import (  # noqa: E402
    MODE1_SYNC,
    extract_mode1_payload,
)
from game_layout import (  # noqa: E402
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    absolute_lba,
    bank_for_offset,
    payload_offset,
)
from render_pce_tiles import decode_tile  # noqa: E402


class GameLayoutTests(unittest.TestCase):
    """Verify shared payload-coordinate and bank-boundary invariants."""

    def test_bank_boundaries_are_half_open(self) -> None:
        """Assign the last old-bank byte and first new-bank byte correctly."""

        self.assertEqual(bank_for_offset(0), "MISSION_0")
        self.assertEqual(bank_for_offset(5376 * SECTOR_SIZE - 1), "MISSION_0")
        self.assertEqual(bank_for_offset(5376 * SECTOR_SIZE), "MISSION_1")

    def test_coordinate_helpers(self) -> None:
        """Convert payload and absolute-disc coordinates deterministically."""

        self.assertEqual(payload_offset(3, 0x123), 3 * SECTOR_SIZE + 0x123)
        self.assertEqual(absolute_lba(0), 3590)
        self.assertEqual(absolute_lba(100), 3690)


class DialogueParserTests(unittest.TestCase):
    """Verify glyph, control, termination, and argument parsing behavior."""

    def test_shift_jis_and_control_tokens_remain_distinct(self) -> None:
        """Preserve a control tag without adding it to visible source text."""

        data = (
            "猫".encode("shift_jis")
            + b"\x40"
            + "犬".encode("shift_jis")
            + b"\x00"
        )
        parsed = parse_record(data, 0)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual("".join(parsed.text_only), "猫犬")
        self.assertEqual("".join(parsed.tokens), "猫<$40>犬")
        self.assertEqual(parsed.controls, (0x40,))
        self.assertEqual(parsed.end_offset, len(data) - 1)

    def test_unterminated_candidate_is_rejected(self) -> None:
        """Return ``None`` when no null terminator exists within the data."""

        self.assertIsNone(parse_record("未完".encode("shift_jis"), 0))

    def test_invalid_bounds_raise_value_error(self) -> None:
        """Reject negative starts and non-positive scan limits explicitly."""

        with self.assertRaises(ValueError):
            parse_record(b"\x00", -1)
        with self.assertRaises(ValueError):
            parse_record(b"\x00", 0, limit=0)


class RangeTests(unittest.TestCase):
    """Verify interval normalization and resource-name heuristics."""

    def test_overlapping_and_adjacent_ranges_are_merged(self) -> None:
        """Coalesce touching ranges and discard empty input intervals."""

        self.assertEqual(
            merge_ranges([(20, 30), (0, 10), (8, 20), (40, 40)]),
            [(0, 30)],
        )

    def test_resource_name_filter_rejects_fill(self) -> None:
        """Retain plausible identifiers while rejecting repeated fill."""

        self.assertTrue(looks_like_resource_name("BARTEN1"))
        self.assertTrue(looks_like_resource_name("AF01"))
        self.assertFalse(looks_like_resource_name("UUUUUUUU"))
        self.assertFalse(looks_like_resource_name("MixedCase"))


class TileDecoderTests(unittest.TestCase):
    """Verify PC Engine planar tile decoding."""

    def test_four_bitplanes_form_palette_index(self) -> None:
        """Combine the four high bits into palette index 15 at pixel zero."""

        tile = bytearray(32)
        tile[0] = tile[1] = tile[16] = tile[17] = 0x80
        pixels = decode_tile(bytes(tile))
        self.assertEqual(len(pixels), 64)
        self.assertEqual(pixels[0], 15)
        self.assertTrue(all(pixel == 0 for pixel in pixels[1:]))


class Mode1ExtractionTests(unittest.TestCase):
    """Verify safe extraction from synthetic raw Mode 1 sectors."""

    def test_one_structurally_valid_sector_is_extracted(self) -> None:
        """Write exactly the 2048-byte user-data area and its digest."""

        payload = bytes((index % 251 for index in range(SECTOR_SIZE)))
        raw = bytearray(RAW_SECTOR_SIZE)
        raw[: len(MODE1_SYNC)] = MODE1_SYNC
        raw[15] = 1
        raw[
            MODE1_USER_DATA_OFFSET : MODE1_USER_DATA_OFFSET + SECTOR_SIZE
        ] = payload

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = pathlib.Path(temporary_directory)
            image = temporary / "synthetic.img"
            output = temporary / "payload.bin"
            image.write_bytes(raw)
            written, digest = extract_mode1_payload(
                image, output, start_lba=0, sector_count=1
            )

            self.assertEqual(written, SECTOR_SIZE)
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
