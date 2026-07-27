"""Regression tests for documented binary-format behavior.

These tests use synthetic bytes.  They are fast enough to run after every code
edit and do not require redistributing or copying the game image.
"""

from __future__ import annotations

import hashlib
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
    HUMAN_TEST_BINARY_PATCHES,
    HUMAN_TEST_PATCHES,
    INFORMATION_HIDDEN_ROW,
    INFORMATION_SCREEN_LAYOUT_PATCHES,
    INFORMATION_SCREEN_LINES,
    MISSION0_PROLOGUE_PATCHES,
    MISSION0_RENDERER_PATCHES,
    MISSION_TITLE_PATCHES,
    OPENING_PROFILE_FIELDS,
    OPENING_PROFILE_LAYOUT_PATCHES,
    OPENING_PROFILE_TEXT_PATCHES,
    PROLOGUE_WRAP_WIDTH,
    TITLE_ASSET_BYTES,
    TITLE_PALETTE_OFFSET,
    TITLE_SCREEN_OFFSET,
    ascii_to_fullwidth,
    optional_title_screen_patches,
    profile_relative_sectors,
    wrap_ascii_text,
)
from cdrom_mode1 import (  # noqa: E402
    MODE1_SYNC,
    PayloadPatch,
    apply_payload_patches,
    compute_edc,
    mode1_integrity_matches,
    read_payload_range,
    rebuild_mode1_sector,
)
from dialogue_relocation import (  # noqa: E402
    DIALOGUE_MARKER,
    DialoguePage,
    DialogueRelocationPlan,
    PageBreakPlan,
    PageGeometry,
    PointerSite,
    RelocationArea,
    ascii_to_fullwidth_sjis,
    find_u16_pointer_candidates,
    wrap_dialogue_page,
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
from pce_graphics import decode_tile, encode_tile  # noqa: E402
from title_screen import (  # noqa: E402
    BACKGROUND_INDEX,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TITLE_PALETTE_BYTES,
    TITLE_PALETTE_COLORS,
    TITLE_PALETTE_LEVELS,
    TITLE_PALETTE_FRAMES,
    TITLE_FIRST_VISIBLE_INDEX,
    TITLE_SUBTITLE,
    build_clean_title_asset,
    build_clean_title_pixels,
    build_grayscale_title_palette_cycle,
    encode_title_pixels,
    title_palette_index,
)


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
    """Verify PC Engine planar tile encoding and decoding."""

    def test_four_bitplanes_form_palette_index(self) -> None:
        """Combine the four high bits into palette index 15 at pixel zero."""

        tile = bytearray(32)
        tile[0] = tile[1] = tile[16] = tile[17] = 0x80
        pixels = decode_tile(bytes(tile))
        self.assertEqual(len(pixels), 64)
        self.assertEqual(pixels[0], 15)
        self.assertTrue(all(pixel == 0 for pixel in pixels[1:]))

    def test_encoder_is_the_exact_inverse_of_decoder(self) -> None:
        """Round-trip all four bitplanes without losing pixel indexes."""

        pixels = [(index * 7) % 16 for index in range(64)]
        encoded = encode_tile(pixels)
        self.assertEqual(len(encoded), 32)
        self.assertEqual(decode_tile(encoded), pixels)

    def test_encoder_rejects_invalid_pixels(self) -> None:
        """Reject malformed tile dimensions and palette indexes."""

        with self.assertRaises(ValueError):
            encode_tile([0] * 63)
        with self.assertRaises(ValueError):
            encode_tile([0] * 63 + [16])


class TitleScreenTests(unittest.TestCase):
    """Verify the generated title asset and optional profile boundary."""

    def test_generated_asset_is_stable_and_decodes_losslessly(self) -> None:
        """Keep the reviewed 256-by-240 title layout byte-exact."""

        pixels = build_clean_title_pixels()
        asset = build_clean_title_asset()
        self.assertEqual(len(pixels), SCREEN_WIDTH * SCREEN_HEIGHT)
        self.assertEqual(len(asset), TITLE_ASSET_BYTES)
        self.assertEqual(
            hashlib.sha256(asset).hexdigest(),
            "f8e91ad827040796ea63a80541e06f71"
            "159ca18121b10ab5128347ad6206e8f1",
        )

        decoded = [BACKGROUND_INDEX] * len(pixels)
        for tile_index in range(len(asset) // 32):
            tile = decode_tile(
                asset[tile_index * 32:tile_index * 32 + 32]
            )
            tile_x = tile_index % (SCREEN_WIDTH // 8)
            tile_y = tile_index // (SCREEN_WIDTH // 8)
            for pixel_y in range(8):
                destination = (
                    (tile_y * 8 + pixel_y) * SCREEN_WIDTH
                    + tile_x * 8
                )
                source = pixel_y * 8
                decoded[destination:destination + 8] = (
                    tile[source:source + 8]
                )
        self.assertEqual(decoded, pixels)
        self.assertEqual(pixels[0], BACKGROUND_INDEX)
        self.assertEqual(pixels[-1], BACKGROUND_INDEX)

    def test_embedded_mask_retains_approved_title_identity(self) -> None:
        """Keep the reference-derived silhouette and subtitle explicit."""

        self.assertEqual(TITLE_SUBTITLE, "ATTRIBUTE OF THE BEAST")
        pixels = build_clean_title_pixels()
        self.assertEqual(
            set(pixels),
            {BACKGROUND_INDEX, *range(TITLE_FIRST_VISIBLE_INDEX, 16)},
        )
        self.assertEqual(
            sum(pixel != BACKGROUND_INDEX for pixel in pixels),
            10959,
        )
        self.assertEqual(title_palette_index(0), BACKGROUND_INDEX)
        self.assertEqual(title_palette_index(15), 15)
        with self.assertRaises(ValueError):
            title_palette_index(16)
        with self.assertRaises(ValueError):
            encode_title_pixels(pixels[:-1])
        invalid = list(pixels)
        invalid[0] = 16
        with self.assertRaises(ValueError):
            encode_title_pixels(invalid)

    def test_grayscale_palette_replaces_every_color_cycle_frame(self) -> None:
        """Keep antialiased indexes stable throughout title animation."""

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
        self.assertEqual(words[0], 0x000)
        self.assertEqual(words[-1], 0x1FF)
        self.assertEqual(words[:TITLE_FIRST_VISIBLE_INDEX], [0] * 6)
        self.assertEqual(
            words,
            [level * 0x49 for level in TITLE_PALETTE_LEVELS],
        )
        for word in words:
            red = word & 0x07
            green = (word >> 3) & 0x07
            blue = (word >> 6) & 0x07
            self.assertEqual(red, green)
            self.assertEqual(green, blue)

    def test_original_mode_returns_no_cosmetic_patch(self) -> None:
        """Omit title reads and changes when downstream builders opt out."""

        nonexistent = pathlib.Path("source-image-is-not-needed.img")
        self.assertEqual(
            optional_title_screen_patches(nonexistent, "original"),
            (),
        )
        with self.assertRaises(ValueError):
            optional_title_screen_patches(nonexistent, "unsupported")

    def test_title_mode_changes_only_the_expected_sector_span(self) -> None:
        """Add the palette sector and sectors 20-34 in clean mode."""

        original = set(profile_relative_sectors("original"))
        clean = set(profile_relative_sectors("clean"))
        title_first = TITLE_SCREEN_OFFSET // SECTOR_SIZE
        title_last = (
            TITLE_SCREEN_OFFSET + TITLE_ASSET_BYTES - 1
        ) // SECTOR_SIZE
        palette_first = TITLE_PALETTE_OFFSET // SECTOR_SIZE
        palette_last = (
            TITLE_PALETTE_OFFSET + TITLE_PALETTE_BYTES - 1
        ) // SECTOR_SIZE
        self.assertEqual(len(original), 21)
        self.assertEqual(len(clean), 37)
        self.assertEqual(
            clean - original,
            (
                set(range(palette_first, palette_last + 1))
                | set(range(title_first, title_last + 1))
            ),
        )


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

    def test_payload_reader_validates_and_joins_sector_data(self) -> None:
        """Read a cross-sector range without exposing raw-sector metadata."""

        first_payload = bytes(index % 251 for index in range(SECTOR_SIZE))
        second_payload = bytes(
            (index + 17) % 251
            for index in range(SECTOR_SIZE)
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            image = pathlib.Path(temporary_directory) / "synthetic.img"
            image.write_bytes(
                synthetic_mode1_sector(first_payload)
                + synthetic_mode1_sector(second_payload)
            )
            actual = read_payload_range(
                image,
                SECTOR_SIZE - 5,
                12,
                start_lba=0,
                sector_count=2,
            )

        self.assertEqual(
            actual,
            first_payload[-5:] + second_payload[:7],
        )


class DialogueRelocationTests(unittest.TestCase):
    """Verify stock-renderer paging and guarded relocation contracts."""

    @staticmethod
    def page_only_source() -> bytes:
        """Return a synthetic two-page Shift-JIS dialogue record."""

        return (
            DIALOGUE_MARKER
            + "一頁".encode("shift_jis")
            + b"\x40"
            + "二頁".encode("shift_jis")
            + b"\x00"
        )

    def test_page_plan_uses_stock_fullwidth_and_existing_control(
        self,
    ) -> None:
        """Compile explicit lines without introducing a renderer escape."""

        geometry = PageGeometry(width=11, maximum_lines=3)
        plan = PageBreakPlan(
            pages=(
                DialoguePage(("Accurate", "English.")),
                wrap_dialogue_page("Second page.", geometry),
            ),
            source_page_breaks=1,
            geometry=geometry,
        )
        compiled = plan.compile_record(self.page_only_source())
        parsed = parse_record(compiled, len(DIALOGUE_MARKER))

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.controls, (0x40,))
        self.assertIn(
            ascii_to_fullwidth_sjis("Accurate"),
            compiled,
        )
        self.assertNotIn(b"\xFF", compiled)
        self.assertNotIn(b"\xFE", compiled)

    def test_added_pages_require_record_specific_opt_in(self) -> None:
        """Reject silent paging changes but allow an explicit expansion."""

        pages = (
            DialoguePage(("One.",)),
            DialoguePage(("Two.",)),
            DialoguePage(("Three.",)),
        )
        geometry = PageGeometry(width=11, maximum_lines=3)
        with self.assertRaises(ValueError):
            PageBreakPlan(
                pages=pages,
                source_page_breaks=1,
                geometry=geometry,
            )

        plan = PageBreakPlan(
            pages=pages,
            source_page_breaks=1,
            geometry=geometry,
            allow_added_page_breaks=True,
        )
        compiled = plan.compile_record(self.page_only_source())
        parsed = parse_record(compiled, len(DIALOGUE_MARKER))
        self.assertEqual(parsed.controls, (0x40, 0x40))

    def test_page_plan_rejects_mixed_source_controls(self) -> None:
        """Keep waits and input commands out of a page-only compiler."""

        source = (
            DIALOGUE_MARKER
            + "一".encode("shift_jis")
            + b"\x21"
            + "二".encode("shift_jis")
            + b"\x00"
        )
        plan = PageBreakPlan(
            pages=(DialoguePage(("English.",)),),
            source_page_breaks=0,
            geometry=PageGeometry(width=11, maximum_lines=3),
        )
        with self.assertRaises(ValueError):
            plan.compile_record(source)

    def test_relocation_updates_all_pointers_and_keeps_source(
        self,
    ) -> None:
        """Guard the source while updating mapped pointers and owned bytes."""

        source = self.page_only_source()
        replacement = PageBreakPlan(
            pages=(
                DialoguePage(("First.",)),
                DialoguePage(("Second.",)),
            ),
            source_page_breaks=1,
            geometry=PageGeometry(width=11, maximum_lines=3),
        ).compile_record(source)
        area = RelocationArea(
            offset=0x1200,
            expected=b"\x00" * 64,
            resource_start=0x1000,
            resource_end=0x1300,
            alignment=2,
            purpose="synthetic confirmed resource tail",
        )
        pointers = (
            PointerSite(
                offset=0x1010,
                base_offset=0x1000,
                source_offset=0x1080,
                purpose="synthetic table entry A",
            ),
            PointerSite(
                offset=0x1014,
                base_offset=0x1000,
                source_offset=0x1080,
                purpose="synthetic table entry B",
            ),
        )
        plan = DialogueRelocationPlan(
            source_offset=0x1080,
            source_record=source,
            replacement_record=replacement,
            area=area,
            pointers=pointers,
            purpose="synthetic dialogue",
        )
        source_guard, first, second, destination = (
            plan.to_payload_patches()
        )

        self.assertEqual(source_guard.expected, source_guard.replacement)
        self.assertEqual(first.expected, bytes.fromhex("80 00"))
        self.assertEqual(first.replacement, bytes.fromhex("00 02"))
        self.assertEqual(second.replacement, bytes.fromhex("00 02"))
        self.assertTrue(destination.replacement.startswith(replacement))
        self.assertEqual(
            len(destination.expected),
            len(destination.replacement),
        )

    def test_relocation_refuses_unproven_reachability(self) -> None:
        """Require at least one proven pointer before a plan can activate."""

        source = self.page_only_source()
        area = RelocationArea(
            offset=0x1200,
            expected=b"\x00" * 64,
            resource_start=0x1000,
            resource_end=0x1300,
            alignment=1,
            purpose="synthetic owned area",
        )
        with self.assertRaises(ValueError):
            DialogueRelocationPlan(
                source_offset=0x1080,
                source_record=source,
                replacement_record=source,
                area=area,
                pointers=(),
                purpose="unmapped dialogue",
            )

    def test_relocation_rejects_pointer_overlap_with_source(self) -> None:
        """Prevent overlapping source guards and pointer updates."""

        source = self.page_only_source()
        area = RelocationArea(
            offset=0x1200,
            expected=b"\x00" * 64,
            resource_start=0x1000,
            resource_end=0x1300,
            alignment=1,
            purpose="synthetic owned area",
        )
        pointer = PointerSite(
            offset=0x1082,
            base_offset=0x1000,
            source_offset=0x1080,
            purpose="invalid embedded pointer",
        )
        with self.assertRaises(ValueError):
            DialogueRelocationPlan(
                source_offset=0x1080,
                source_record=source,
                replacement_record=source,
                area=area,
                pointers=(pointer,),
                purpose="overlapping dialogue",
            )

    def test_pointer_scanner_reports_candidates_without_claiming_proof(
        self,
    ) -> None:
        """Return bounded byte matches for later structural review."""

        data = bytearray(b"\x00" * 64)
        data[8:10] = bytes.fromhex("20 00")
        data[20:22] = bytes.fromhex("20 00")
        self.assertEqual(
            find_u16_pointer_candidates(
                bytes(data),
                target_offset=0x1020,
                base_offset=0x1000,
                search_start=0,
                search_end=len(data),
                alignment=2,
            ),
            (8, 20),
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

    def test_v9_profile_is_same_size_and_in_expected_sectors(self) -> None:
        """Keep all v0.9 text replacements within reviewed payload sectors."""

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
        self.assertEqual(len(HUMAN_TEST_PATCHES), 271)
        self.assertEqual(
            sectors,
            {
                3,
                4,
                12,
                13,
                65,
                66,
                67,
                193,
                194,
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

    def test_opening_profiles_cover_both_banks_without_overlap(self) -> None:
        """Translate and reflow every visible field in all seven dossiers."""

        self.assertEqual(len(OPENING_PROFILE_FIELDS), 80)
        self.assertEqual(len(OPENING_PROFILE_TEXT_PATCHES), 160)
        self.assertEqual(len(OPENING_PROFILE_LAYOUT_PATCHES), 46)
        self.assertEqual(
            {field.profile for field in OPENING_PROFILE_FIELDS},
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
        for field in OPENING_PROFILE_FIELDS:
            self.assertEqual(len(field.offsets), 2)
            for patch in field.to_text_patches():
                payload_patch = patch.to_payload_patch()
                self.assertEqual(
                    len(payload_patch.expected),
                    len(payload_patch.replacement),
                )

        for profile in {field.profile for field in OPENING_PROFILE_FIELDS}:
            rows = sorted(
                field.display_row
                for field in OPENING_PROFILE_FIELDS
                if field.profile == profile and field.english
            )
            self.assertEqual(len(rows), len(set(rows)))
            self.assertTrue(
                all(
                    next_row - row >= 2
                    for row, next_row in zip(rows, rows[1:])
                )
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

    def test_stock_renderer_profile_has_no_code_patches(self) -> None:
        """Keep parser, glyph, cursor, and punctuation code byte-identical."""

        self.assertEqual(MISSION0_RENDERER_PATCHES, ())
        self.assertEqual(
            len(HUMAN_TEST_BINARY_PATCHES),
            len(OPENING_PROFILE_LAYOUT_PATCHES)
            + len(INFORMATION_SCREEN_LAYOUT_PATCHES),
        )
        retired_ranges = (
            range(0x00137165, 0x00137168),
            range(0x00136D0E, 0x00136D24),
        )
        for patch in HUMAN_TEST_BINARY_PATCHES:
            patch_range = range(patch.offset, patch.end_offset)
            for retired_range in retired_ranges:
                self.assertTrue(
                    patch_range.stop <= retired_range.start
                    or retired_range.stop <= patch_range.start
                )

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
        self.assertEqual(len(INFORMATION_SCREEN_LAYOUT_PATCHES), 34)
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
        """Reveal consistently aligned lines without vertical overlap."""

        for screen in {"video", "novel", "music"}:
            visible_lines = [
                line
                for line in INFORMATION_SCREEN_LINES
                if line.screen == screen and line.english
            ]
            rows = [
                line.display_row
                for line in visible_lines
            ]
            self.assertTrue(all(row <= 0x18 for row in rows))
            self.assertEqual(len(rows), len(set(rows)))
            self.assertTrue(
                all(
                    next_row - row >= 2
                    for row, next_row in zip(rows, rows[1:])
                )
            )
            body_lines = [
                line
                for line in visible_lines
                if line.display_row >= 0x08
            ]
            self.assertTrue(
                all(
                    line.english.startswith("   ")
                    and not line.english.startswith("    ")
                    for line in body_lines
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
