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
from build_human_test_disc import (  # noqa: E402
    BOOT_MENU_PATCHES,
    HUMAN_TEST_PATCHES,
    INFORMATION_HIDDEN_ROW,
    INFORMATION_SCREEN_LAYOUT_PATCHES,
    INFORMATION_SCREEN_LINES,
    MISSION0_PROLOGUE_PATCHES,
    MISSION0_RENDERER_PATCHES,
    MISSION_TITLE_PATCHES,
    PROLOGUE_WRAP_WIDTH,
    ascii_to_fullwidth,
    wrap_ascii_text,
)
from cdrom_mode1 import (  # noqa: E402
    MODE1_SYNC,
    PayloadPatch,
    apply_payload_patches,
    compute_edc,
    mode1_integrity_matches,
    rebuild_mode1_sector,
)
from extract_auxiliary_text import merge_ranges  # noqa: E402
from extract_dialogue import parse_record  # noqa: E402
from extract_track2_mode1 import extract_mode1_payload  # noqa: E402
from disassemble_huc6280 import (  # noqa: E402
    OPCODES,
    decode_instruction,
    linear_disassemble,
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


def synthetic_mode1_sector(payload: bytes) -> bytes:
    """Return one rebuilt synthetic Mode 1 sector.

    Args:
        payload: Exact 2048-byte user-data area.

    Returns:
        Structurally valid raw sector with current EDC and ECC fields.

    Raises:
        ValueError: If ``payload`` does not contain exactly 2048 bytes.
    """

    if len(payload) != SECTOR_SIZE:
        raise ValueError("synthetic payload must contain 2048 bytes")
    raw = bytearray(RAW_SECTOR_SIZE)
    raw[: len(MODE1_SYNC)] = MODE1_SYNC
    raw[15] = 1
    raw[
        MODE1_USER_DATA_OFFSET:
        MODE1_USER_DATA_OFFSET + SECTOR_SIZE
    ] = payload
    return rebuild_mode1_sector(raw)


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


class Mode1RebuildTests(unittest.TestCase):
    """Verify CD-ROM EDC/ECC rebuilding and guarded payload patching."""

    def test_edc_standard_check_vector(self) -> None:
        """Match the known CD-ROM EDC for the standard numeric vector."""

        self.assertEqual(compute_edc(b"123456789"), 0x6EC2EDC4)

    def test_rebuild_detects_and_repairs_changed_user_data(self) -> None:
        """Detect stale parity and restore it after a payload edit."""

        payload = bytes(index % 251 for index in range(SECTOR_SIZE))
        valid = synthetic_mode1_sector(payload)
        self.assertTrue(mode1_integrity_matches(valid))

        damaged = bytearray(valid)
        damaged[MODE1_USER_DATA_OFFSET + 100] ^= 0xFF
        self.assertFalse(mode1_integrity_matches(damaged))
        self.assertTrue(
            mode1_integrity_matches(rebuild_mode1_sector(damaged))
        )

    def test_cross_sector_patch_rebuilds_both_sectors(self) -> None:
        """Apply one guarded patch that crosses a payload boundary."""

        first_payload = bytes(
            index % 251
            for index in range(SECTOR_SIZE)
        )
        second_payload = bytes(
            (index + 31) % 251
            for index in range(SECTOR_SIZE)
        )
        expected = first_payload[-8:] + second_payload[:8]
        patch = PayloadPatch(
            offset=SECTOR_SIZE - 8,
            expected=expected,
            replacement=b"Z" * len(expected),
            label="synthetic cross-sector patch",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            image = pathlib.Path(temporary_directory) / "synthetic.img"
            image.write_bytes(
                synthetic_mode1_sector(first_payload)
                + synthetic_mode1_sector(second_payload)
            )
            reports = apply_payload_patches(
                image,
                (patch,),
                start_lba=0,
                sector_count=2,
            )
            raw = image.read_bytes()

        self.assertEqual(
            [report.relative_sector for report in reports],
            [0, 1],
        )
        self.assertTrue(
            mode1_integrity_matches(raw[:RAW_SECTOR_SIZE])
        )
        self.assertTrue(
            mode1_integrity_matches(raw[RAW_SECTOR_SIZE:])
        )
        first_end = MODE1_USER_DATA_OFFSET + SECTOR_SIZE
        self.assertEqual(raw[first_end - 8:first_end], b"Z" * 8)
        second_start = RAW_SECTOR_SIZE + MODE1_USER_DATA_OFFSET
        self.assertEqual(
            raw[second_start:second_start + 8],
            b"Z" * 8,
        )


class HumanTestProfileTests(unittest.TestCase):
    """Verify the startup and Mission 0 human-test profiles."""

    def test_v1_profile_stays_in_original_sectors(self) -> None:
        """Keep the preserved v0.1 replacements in payload sectors 3 and 4."""

        sectors: set[int] = set()
        for text_patch in BOOT_MENU_PATCHES:
            patch = text_patch.to_payload_patch()
            self.assertEqual(
                len(patch.expected),
                len(patch.replacement),
            )
            first_sector = patch.offset // SECTOR_SIZE
            last_sector = (
                patch.end_offset - 1
            ) // SECTOR_SIZE
            sectors.update(
                range(first_sector, last_sector + 1)
            )
        self.assertEqual(sectors, {3, 4})

    def test_v7_profile_is_same_size_and_in_expected_sectors(self) -> None:
        """Keep all v0.7 replacements within reviewed payload sectors."""

        sectors: set[int] = set()
        for text_patch in HUMAN_TEST_PATCHES:
            patch = text_patch.to_payload_patch()
            self.assertEqual(
                len(patch.expected),
                len(patch.replacement),
            )
            first_sector = patch.offset // SECTOR_SIZE
            last_sector = (
                patch.end_offset - 1
            ) // SECTOR_SIZE
            sectors.update(
                range(first_sector, last_sector + 1)
            )
        self.assertEqual(len(HUMAN_TEST_PATCHES), 111)
        self.assertEqual(
            sectors,
            {
                3,
                4,
                12,
                13,
                651,
                747,
                6692,
                12163,
                17624,
                22100,
                26313,
                30340,
                34079,
                36786,
                37030,
                37036,
            },
        )

    def test_v7_profile_does_not_overwrite_known_controls(self) -> None:
        """Protect title, line-break, and dialogue-terminator bytes."""

        control_offsets = {
            0x001458E4,
            0x00145BAA,
            0x00145BEC,
        }
        for title_patch in MISSION_TITLE_PATCHES:
            payload_patch = title_patch.to_payload_patch()
            control_offsets.add(title_patch.offset - 1)
            control_offsets.add(payload_patch.end_offset)
        for prologue_patch in MISSION0_PROLOGUE_PATCHES:
            payload_patch = prologue_patch.to_payload_patch()
            control_offsets.add(prologue_patch.offset - 1)
            control_offsets.add(payload_patch.end_offset)

        for text_patch in HUMAN_TEST_PATCHES:
            patch = text_patch.to_payload_patch()
            patch_range = range(patch.offset, patch.end_offset)
            for control_offset in control_offsets:
                self.assertNotIn(control_offset, patch_range)

    def test_v6_renderer_patch_is_guarded_and_page_local(self) -> None:
        """Keep the punctuation hook same-size and in one mapped CPU page."""

        self.assertEqual(len(MISSION0_RENDERER_PATCHES), 2)
        for patch in MISSION0_RENDERER_PATCHES:
            self.assertEqual(len(patch.expected), len(patch.replacement))
            self.assertEqual(
                (patch.offset - 0x00131800) // 0x2000,
                2,
            )
        hook, cave = MISSION0_RENDERER_PATCHES
        self.assertEqual(hook.replacement, bytes.fromhex("4C 0E 55"))
        self.assertEqual(cave.expected, b"\x00" * 22)
        self.assertIn(bytes.fromhex("C9 43"), cave.replacement)
        self.assertIn(bytes.fromhex("C9 44"), cave.replacement)

    def test_information_screen_source_records_are_complete(self) -> None:
        """Cover every translated line in the three merchandise pages."""

        self.assertEqual(len(INFORMATION_SCREEN_LINES), 43)
        self.assertEqual(
            {
                line.screen
                for line in INFORMATION_SCREEN_LINES
            },
            {"video", "novel", "music"},
        )
        self.assertEqual(len(INFORMATION_SCREEN_LAYOUT_PATCHES), 33)
        for line in INFORMATION_SCREEN_LINES:
            text_patch = line.to_text_patch().to_payload_patch()
            self.assertEqual(
                len(text_patch.expected),
                len(text_patch.replacement),
            )
            self.assertEqual(
                line.command_offset + 3,
                line.text_offset,
            )

    def test_information_screen_visible_rows_do_not_overlap(self) -> None:
        """Separate every visible 16-pixel line by two tile rows."""

        for screen in {"video", "novel", "music"}:
            rows = sorted(
                line.display_row
                for line in INFORMATION_SCREEN_LINES
                if line.screen == screen and line.english
            )
            self.assertTrue(all(row <= 0x16 for row in rows))
            self.assertEqual(len(rows), len(set(rows)))
            self.assertTrue(
                all(
                    next_row - row >= 2
                    for row, next_row in zip(rows, rows[1:])
                )
            )

    def test_information_screen_cleared_rows_are_offscreen(self) -> None:
        """Move superseded records below the visible 30-row field."""

        cleared = [
            line
            for line in INFORMATION_SCREEN_LINES
            if not line.english
        ]
        self.assertTrue(cleared)
        self.assertTrue(
            all(
                line.display_row == INFORMATION_HIDDEN_ROW
                for line in cleared
            )
        )

    def test_fullwidth_conversion_rejects_control_characters(self) -> None:
        """Keep replacement text out of the low-byte control range."""

        self.assertEqual(
            ascii_to_fullwidth("A 1!"),
            "Ａ　１！",
        )
        self.assertEqual(
            ascii_to_fullwidth("A-B'S"),
            "Ａ−Ｂ’Ｓ",
        )
        with self.assertRaises(ValueError):
            ascii_to_fullwidth("line\nbreak")

    def test_word_wrap_pads_only_completed_lines(self) -> None:
        """Wrap words by cell without inserting a control or newline."""

        exact = wrap_ascii_text(
            "I hunt crooks and turn them in.",
            PROLOGUE_WRAP_WIDTH,
        )
        self.assertEqual(
            [
                exact[:11],
                exact[11:22],
                exact[22:33],
                exact[33:],
            ],
            ["I hunt     ", "crooks and ", "turn them  ", "in."],
        )

        padded = wrap_ascii_text(
            "His trail led me back to Oedo.",
            PROLOGUE_WRAP_WIDTH,
        )
        self.assertEqual(
            [padded[:11], padded[11:22], padded[22:]],
            ["His trail  ", "led me back", "to Oedo."],
        )

    def test_word_wrap_rejects_ambiguous_input(self) -> None:
        """Reject widths and spacing that make cell wrapping ambiguous."""

        with self.assertRaises(ValueError):
            wrap_ascii_text("Text", 0)
        with self.assertRaises(ValueError):
            wrap_ascii_text("two  spaces", 13)
        with self.assertRaises(ValueError):
            wrap_ascii_text("overlongword", 5)


class HuC6280DisassemblerTests(unittest.TestCase):
    """Verify deterministic HuC6280 instruction decoding."""

    def test_opcode_table_covers_every_byte(self) -> None:
        """Keep the opcode matrix complete and in numeric order."""

        self.assertEqual(len(OPCODES), 256)
        self.assertEqual(OPCODES[0x20], ("jsr", "abs"))
        self.assertEqual(OPCODES[0x73], ("tii", "blk"))
        self.assertEqual(OPCODES[0xF4], ("set", "imp"))

    def test_decode_formats_absolute_and_relative_targets(self) -> None:
        """Format calls and signed branch targets from logical addresses."""

        call = decode_instruction(
            bytes.fromhex("20 60 E0"),
            0,
            0x00136589,
            0x4D89,
        )
        branch = decode_instruction(
            bytes.fromhex("80 EA"),
            0,
            0x00072EDF,
            0x66DF,
        )
        self.assertEqual(call.operand, "$E060")
        self.assertEqual(branch.operand, "$66CB")

    def test_linear_disassembly_retains_both_coordinate_systems(self) -> None:
        """Advance payload and CPU coordinates by instruction length."""

        instructions = list(
            linear_disassemble(
                bytes.fromhex("A9 0B 60"),
                0x00137165,
                0x5965,
            )
        )
        self.assertEqual(
            [
                (item.payload_offset, item.cpu_address, item.mnemonic)
                for item in instructions
            ],
            [
                (0x00137165, 0x5965, "lda"),
                (0x00137167, 0x5967, "rts"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
