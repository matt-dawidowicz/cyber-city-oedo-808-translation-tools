"""Assemble the maintained stock-renderer human-test build profile."""

from __future__ import annotations

import hashlib
import pathlib

from cyber_oedo.build.profiles.dossiers import (
    OPENING_PROFILE_FIELDS,
    OPENING_PROFILE_LAYOUT_PATCHES,
    OPENING_PROFILE_TEXT_PATCHES,
)
from cyber_oedo.build.profiles.media_mix import (
    INFORMATION_HIDDEN_ROW,
    INFORMATION_SCREEN_LAYOUT_PATCHES,
    INFORMATION_SCREEN_LINES,
    INFORMATION_SCREEN_TEXT_PATCHES,
)
from cyber_oedo.build.profiles.models import (
    InPlaceTextPatch,
    InformationScreenLine,
    OpeningProfileField,
    ascii_to_fullwidth,
    wrap_ascii_text,
)
from cyber_oedo.build.profiles.startup import (
    BOOT_MENU_PATCHES,
    MISSION0_DIALOGUE_PATCHES,
    MISSION0_PROLOGUE_PATCHES,
    MISSION_TITLE_PATCHES,
    PROLOGUE_WRAP_WIDTH,
    STARTUP_V2_EXTRA_PATCHES,
)
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch, read_payload_range
from cyber_oedo.disc.game_layout import (
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)
from cyber_oedo.graphics.title_screen import (
    TITLE_ASSET_BYTES,
    TITLE_PALETTE_BYTES,
    build_clean_title_asset,
    build_grayscale_title_palette_cycle,
)


BUILD_PROFILE = 'mission0-stock-renderer'


OUTPUT_STEM = 'Cyber City Oedo 808 - Kemono no Alignment (Japan) [Stock Renderer Test]'


TITLE_SCREEN_OFFSET = 40960


TITLE_PALETTE_OFFSET = 10312


TITLE_SCREEN_MODES = ('clean', 'original')


DEFAULT_TITLE_SCREEN_MODE = 'clean'


TITLE_SCREEN_SOURCE_SHA256 = '74319e81bfeba32b385620a8bf32848e78da19271c87b6337decf4991a2fe5c4'


TITLE_PALETTE_SOURCE_SHA256 = '650a61cee3f91e3c4b2a5159feb38800384daa2ad6ba48903f3596417fa1085b'


SOURCE_HASHES = {'.ccd': '716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b', '.img': '815a8dda33ba2bb046fcbde773ad3a80fc6f89a96ef07e9c06bcc1c2e5fddece', '.sub': 'ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411'}


HUMAN_TEST_PATCHES = BOOT_MENU_PATCHES + STARTUP_V2_EXTRA_PATCHES + MISSION_TITLE_PATCHES + MISSION0_DIALOGUE_PATCHES + MISSION0_PROLOGUE_PATCHES + OPENING_PROFILE_TEXT_PATCHES + INFORMATION_SCREEN_TEXT_PATCHES


MISSION0_RENDERER_PATCHES: tuple[PayloadPatch, ...] = ()


HUMAN_TEST_BINARY_PATCHES = OPENING_PROFILE_LAYOUT_PATCHES + INFORMATION_SCREEN_LAYOUT_PATCHES


def optional_title_screen_patches(source_image: pathlib.Path, mode: str) -> tuple[PayloadPatch, ...]:
    """Build the isolated optional opening-title and palette replacements.

    Args:
        source_image: Authenticated raw CloneCD IMG used to obtain the original
            title bytes for the guarded patch.
        mode: ``"clean"`` to generate the replacement or ``"original"`` to
            leave the title payload untouched.

    Returns:
        Two same-size patches in clean mode: one seven-frame grayscale palette
        cycle and one title-screen tile block. Original mode returns an empty
        tuple.

    Raises:
        OSError: If the clean mode cannot read the source image.
        ValueError: If the mode is unsupported or the title block differs
            from the analyzed release.

    Side Effects:
        Clean mode reads and validates the palette cycle and 15 title sectors.
        Original mode does not open the image.

    Design Decisions:
        Original bytes are read from the user's authenticated disc rather than
        committed to this open-source repository. Independent palette and
        graphic hashes prevent valid-size but wrong source data from becoming
        unsafe guards. The portrait palette at ``0x2828`` is outside the
        patched range. Returning no patch in original mode makes opt-out
        behavior explicit: translation and layout patches remain otherwise
        identical.
    """
    if mode not in TITLE_SCREEN_MODES:
        raise ValueError(f'title screen must be one of {TITLE_SCREEN_MODES}, found {mode!r}')
    if mode == 'original':
        return ()
    original_palette = read_payload_range(source_image, TITLE_PALETTE_OFFSET, TITLE_PALETTE_BYTES, start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT)
    palette_digest = hashlib.sha256(original_palette).hexdigest()
    if palette_digest != TITLE_PALETTE_SOURCE_SHA256:
        raise ValueError(f'opening title palette differs from the analyzed release: expected {TITLE_PALETTE_SOURCE_SHA256}, found {palette_digest}')
    original = read_payload_range(source_image, TITLE_SCREEN_OFFSET, TITLE_ASSET_BYTES, start_lba=TRACK2_START_LBA, sector_count=TRACK2_SECTOR_COUNT)
    digest = hashlib.sha256(original).hexdigest()
    if digest != TITLE_SCREEN_SOURCE_SHA256:
        raise ValueError(f'opening title graphic differs from the analyzed release: expected {TITLE_SCREEN_SOURCE_SHA256}, found {digest}')
    replacement = build_clean_title_asset()
    return (PayloadPatch(offset=TITLE_PALETTE_OFFSET, expected=original_palette, replacement=build_grayscale_title_palette_cycle(), label='optional antialiased opening title palette'), PayloadPatch(offset=TITLE_SCREEN_OFFSET, expected=original, replacement=replacement, label='optional antialiased opening title graphic'))


def relative_sectors_for_patches(patches: tuple[PayloadPatch, ...]) -> set[int]:
    """Return every payload sector intersected by guarded patches.

    Args:
        patches: Same-size payload patches in any order.

    Returns:
        Set of relative 2048-byte sector indexes. An empty patch tuple returns
        an empty set.

    Notes:
        Counting the complete span matters for large graphic replacements;
        using only each patch's starting sector would under-report the title
        patch by 14 sectors.
    """
    sectors: set[int] = set()
    for patch in patches:
        first_sector = patch.offset // SECTOR_SIZE
        last_sector = (patch.end_offset - 1) // SECTOR_SIZE
        sectors.update(range(first_sector, last_sector + 1))
    return sectors


def profile_relative_sectors(title_screen_mode: str) -> tuple[int, ...]:
    """Return payload sectors guarded by one build variant.

    Args:
        title_screen_mode: ``"clean"`` or ``"original"``.

    Returns:
        Sorted relative sector indexes for all text, layout, and
        optional title-screen patches. A guarded sector can remain
        byte-identical when its source and replacement slices already match.

    Raises:
        ValueError: If the requested title-screen mode is unsupported.

    Design Decisions:
        This source-independent helper describes the patch footprint without
        retaining the 30,720 source bytes used by the title guard. The
        completed build manifest remains authoritative for sectors that
        actually differ.
    """
    if title_screen_mode not in TITLE_SCREEN_MODES:
        raise ValueError('title screen must be clean or original')
    patches = tuple((text_patch.to_payload_patch() for text_patch in HUMAN_TEST_PATCHES)) + HUMAN_TEST_BINARY_PATCHES
    sectors = relative_sectors_for_patches(patches)
    if title_screen_mode == 'clean':
        for offset, byte_count in ((TITLE_PALETTE_OFFSET, TITLE_PALETTE_BYTES), (TITLE_SCREEN_OFFSET, TITLE_ASSET_BYTES)):
            first_sector = offset // SECTOR_SIZE
            last_sector = (offset + byte_count - 1) // SECTOR_SIZE
            sectors.update(range(first_sector, last_sector + 1))
    return tuple(sorted(sectors))


def build_tester_readme(ccd_name: str, title_screen_mode: str) -> str:
    """Return the human-testing instructions included beside the image.

    Args:
        ccd_name: Filename testers should open in an emulator.
        title_screen_mode: Selected ``"clean"`` or ``"original"`` variant.

    Returns:
        Plain-text instructions with scope, boot steps, visible proof, and
        limitations.

    Raises:
        ValueError: If the title-screen mode is unsupported.
    """
    if title_screen_mode not in TITLE_SCREEN_MODES:
        raise ValueError('title screen must be clean or original')
    title_expectation = '- The opening uses the antialiased generated title graphic and artifact-safe grayscale palette.' if title_screen_mode == 'clean' else '- The opening retains the original title graphic.'
    lines = ['Cyber City Oedo 808 - Stock Renderer Test', '===========================================', '', 'Purpose', '-------', 'This is a same-size Shift-JIS Mission 0 vertical slice.', 'It is not a complete English translation.', '', 'How to boot', '-----------', f'1. Keep the CCD, IMG, and SUB together.', f'2. Open this descriptor in a PC Engine CD emulator: {ccd_name}', '3. Use a legally obtained Japanese System Card 3.0 BIOS.', '4. Do not rename only one member of the CloneCD set.', '', 'Expected visible proof', '----------------------', '- The first notice heading reads TEST DISC.', title_expectation, '- The clean title subtitle reads ATTRIBUTE OF THE BEAST.', '- The notice identifies a HUMAN TEST BUILD.', '- Startup, load, and memory prompts use fullwidth English.', '- Mission 1 through Mission 8 title subtitles use English.', '- Both banks of all seven opening criminal profiles use English.', '- Profile text uses non-overlapping 16-pixel row spacing.', '- The opening Mission 0 bartender conversation uses English.', "- Sengoku's complete ten-page opening narration uses English.", '- All three Media Mix merchandise pages use readable English.', '- Merchandise lines use non-overlapping 16-pixel row spacing.', '- Mission 0 dialogue uses lowercase letters.', "- Narration words wrap on the renderer's 11-cell grid.", '- English punctuation stays inside the ordinary 11-cell limit.', '- Most other dialogue and interfaces remain Japanese.', '', 'Human test checklist', '--------------------', '- Boot through the initial notice.', '- Start a new game and reach playable Mission 0.', '- Return to or reopen the startup menu.', '- Exercise DATA LOAD with and without a save.', '- Exercise MEMORYCHECK.', '- Confirm audio begins and later CD audio still plays.', '- Save when the game permits it, restart, and reload.', '- Record emulator name/version, BIOS hash, screenshots, and failures.', '', 'Technical scope', '---------------', '- Source CCD and SUB are copied byte-for-byte.', '- The manifest lists every changed Track 2 payload sector.', '- Raw Mode 1 EDC and ECC are regenerated for changed sectors.', '- Track starts, pregaps, audio sectors, and subchannels are unchanged.', '', 'Known limitations', '-----------------', '- English is fullwidth 16x16 text using the existing BIOS font path.', '- The existing renderer still fits only 11 fullwidth cells per line.', '- No parser, glyph, cursor, or punctuation code is patched.', '- Accurate longer English requires mapped relocation and more pages.', '- The title graphic is an optional cosmetic patch; use --title-screen original to omit it.', '- Media Mix row operands change only to separate 16-pixel glyphs.', '- No pointer, string length, or record terminator is changed.', '- Structural validation passed; emulator behavior needs human testing.', '', 'See build_manifest.json for hashes and exact replacements.', '']
    return '\n'.join(lines)
