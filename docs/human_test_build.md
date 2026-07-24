# Playable human-test build

## Scope

`build_human_test_disc.py` creates a complete, bootable-format CloneCD copy for
the current manual test milestone. The `mission0-v7` profile replaces 111
visible text runs with fullwidth Shift-JIS English:

- 34 startup, load, and memory-state runs;
- 10 mission-title subtitle occurrences;
- 14 segments in the opening Mission 0 bartender exchange; and
- all 10 pages of Sengoku's opening narration; and
- all 43 records across the video, novel, and music Media Mix pages.

This build remains deliberately narrow:

- it uses the original 16x16 System Card font path;
- Mission 0 dialogue uses the game's existing lowercase Latin glyphs;
- narration is word-wrapped at the code-confirmed 11-cell boundary;
- English comma and period use the original hanging-punctuation cell;
- it performs only same-size in-place replacements;
- Media Mix body text is separated onto non-overlapping tile rows;
- it changes 18 reviewed payload sectors and their absolute LBAs;
- it rebuilds the Mode 1 EDC and P/Q ECC for each changed sector;
- it preserves the CCD, SUB, track boundaries, pregaps, and audio sectors; and
- it leaves most dialogue and game text in Japanese.

The output is a structural vertical slice and playtest target. It is not a
complete English translation.

The earlier v0.5 image must not be used for layout review. Its 13-cell padding
assumption was disproved at runtime and caused bad spacing, broken words, and
an orphaned comma. v0.6 was the first build based on the disassembled 11-cell
cursor rule; v0.7 preserves that fix and adds the merchandise pages.

## Why these targets

The startup text remains the quickest proof that the edited data reaches the
screen. Mission titles add broad navigation coverage, while the opening
bartender exchange provides a short, immediately reachable dialogue test. The
complete narration provides the first multi-page end-to-end test and includes
the scene identified in a tester's screenshot. The three Media Mix pages test
a separate row-addressed interface-text path.

The dialogue records do contain low-byte controls. The profile therefore
replaces only independently bounded visible glyph runs and splits a line at
every encountered control. It does not replace, interpret, move, or rename the
controls.

One missing-file string begins at payload offset `0x00001FFC`, four bytes before
the end of sector 3, and continues into sector 4. The builder supports this
cross-sector replacement and rebuilds both raw sectors.

## Required source

Supply a legally obtained CloneCD set whose hashes match
`docs/disc_layout.md`. Keep the `.ccd`, `.img`, and `.sub` together with the
same source stem.

The builder refuses:

- an unknown source hash;
- a missing CloneCD companion;
- pre-existing output directories;
- source text that differs at any patch address;
- a size-changing or overlapping replacement;
- stale EDC/ECC in an affected source sector;
- a change outside the expected raw sectors; or
- any CCD or SUB difference.

## Build command

Run from the repository root:

```powershell
python .\build_human_test_disc.py `
  "C:\path\to\Cyber City Oedo 808 - Kemono no Alignment (Japan).ccd" `
  "C:\path\to\output\cyber_city_oedo_808_human_test_v0.7"
```

The output directory is intentionally required to be new. A successful build
contains:

```text
Cyber City Oedo 808 - Kemono no Alignment (Japan) [Human Test v0.7].ccd
Cyber City Oedo 808 - Kemono no Alignment (Japan) [Human Test v0.7].img
Cyber City Oedo 808 - Kemono no Alignment (Japan) [Human Test v0.7].sub
build_manifest.json
HUMAN_TEST_README.txt
```

Open the `.ccd`, not the `.img`, so the emulator receives the full mixed-mode
track layout.

## What should be visible

The first notice should show:

```text
TEST DISC
THIS GAME HAS 9 MISSIONS
HUMAN TEST BUILD
SAVE ONLY AFTER EACH MISSION
BACKUP MEMORY READY?
NO SPACE TO SAVE!
```

Startup, load, and memory prompts also use fullwidth English. Existing labels
such as `NEWGAME`, `DATALOAD`, and `MEMORYCHECK` are already fullwidth Latin and
remain unchanged.

Mission-title subtitles use short bracketed English labels. In Mission 0, the
first bartender conversation begins with `BART: WELCOME.` and includes the
initial question responses and wait/farewell text. Dialogue after this opening
exchange remains Japanese except for the narration page below.

The ten opening narration pages use lowercase and the following visual lines:

```text
Page 1: Sengoku. / Loner.
Page 2: I hunt / crooks and / turn them / in.
Page 3: Danford aka / Rose Rash,
Page 4: His trail / led me back / to Oedo.
Page 5: Seven years / changed / Oedo. Old / City most / of all.
Page 6: Security / Force takes / Old City.
Page 7: More guns. / It's worse.
Page 8: It begins.
Page 9: Top crooks / evade me,
Page 10: Benten. / Goggles. / Here. Why? / I'll look.
```

The slashes above represent automatic 11-cell wraps, not inserted control
bytes. The formatter pads incomplete lines with fullwidth spaces. Each page
independently fits its original character count. All nine `0x40` page controls,
the `27 28` record marker, and the null terminator remain unchanged.

This wrapping improvement does not increase capacity. The current renderer
still draws one 16x16 glyph per cell. Fitting more than 11 Latin letters on a
line requires an 8x16 or proportional renderer, plus a safe encoding escape so
ordinary ASCII cannot be mistaken for dialogue controls.

The punctuation hook changes the three-byte ordinary-limit return at payload
`0x00137165` into a jump to a 22-byte routine at `0x00136D0E`. Both addresses
are in the active Mission 0 renderer's mapped CPU page. The routine recognizes
only Shift-JIS `81 43` and `81 44`, then returns the existing 12-cell
punctuation limit. Every original Japanese punctuation-table entry is
preserved.

The fullwidth path proves that edited Shift-JIS reaches the screen. It does not
prove that ordinary ASCII is safe; the low-byte dialogue controls remain in
their original locations.

### Media Mix information pages

The information-page interpreter stores each line as ``00 01 RR``, followed by
a null-terminated fullwidth Shift-JIS string. ``RR`` is an 8-pixel tile row,
but the BIOS renders 16-pixel glyphs. The original body uses consecutive row
values, so adjacent Japanese lines overlap.

The v0.7 profile preserves every command opcode, terminator, string byte
capacity, and page boundary. It changes only selected ``RR`` operands:

- visible English rows are separated by at least two tile rows;
- longer English titles reuse the original 30-character box records;
- superseded Japanese fragments and decorative box rows become fullwidth
  spaces on offscreen row ``0x1E``; and
- all visible content remains at or above row ``0x16``.

Expected readable page content is:

```text
Video: Video / LaserDisc; Ancient Memory; The Decoy Program;
       Crimson Media; Y. Kawajiri; Color / Stereo Hi-Fi;
       Japan Home Video; VHS 9600 / LD 7600 + Tax

Novel: Novels; Rebel Lone Wolf; Magnificent Fallen Angel;
       Evil-Eyed Warrior; Fujimi Fantasia Bunko;
       A. Endo / Fujimi Shobo; JPY 500 (Tax Included)

Music: Music CD; Command of Remembrance (OST);
       Criminal Night (Game Music); Compact Disc; King Records;
       JPY 2000 + Tax
```

## Manual test procedure

Use a legally obtained Japanese System Card 3.0 BIOS.

1. Record the emulator name/version and BIOS SHA-256.
2. Boot the output `.ccd`.
3. Photograph or capture the first notice and main menu.
4. Start a new game and enter the opening bar in Mission 0.
5. Exercise every available bartender question and the wait option.
6. Advance through and capture all ten English narration pages.
7. Check each English line for clipping, stale glyphs, or broken paging.
8. Open each of the three Media Mix pages and capture the full screen.
9. Confirm no English information rows touch or overlap vertically.
10. Continue to controllable Mission 0 and confirm CD audio still works.
11. Reopen or reset to the main menu.
12. Exercise `DATALOAD` without a save and `MEMORYCHECK`.
13. When the game permits saving, save, restart, and load.
14. At later mission transitions, confirm the bracketed title subtitles.
15. Record the last successful screen and exact failure behavior, if any.

Compare ambiguous behavior against the unmodified source in the same emulator.

## Structural verification

`build_manifest.json` records:

- source and output hashes;
- exact source and replacement text;
- payload offsets and byte counts;
- relative payload sectors and absolute LBAs;
- before/after hashes for rebuilt raw sectors; and
- every completed automated check.

The builder compares all 249,836 raw sectors. v0.7 success requires the changed
absolute-LBA set to equal:

```text
3593, 3594, 3602, 3603, 4211, 4212, 4241, 4337, 10282, 15753,
21214, 25690, 29903, 33930, 37669, 40376, 40620, 40626
```

`cdrom_mode1.py` implements:

- the reflected CD-ROM EDC polynomial `0xD8018001`;
- Mode 1 little-endian EDC generation;
- the eight reserved zero bytes;
- 172-byte P parity; and
- 104-byte Q parity.

The implementation was compared against original sectors before use and is
covered by synthetic check-vector, stale-parity, repair, and cross-sector
patch tests.

## Editing the test profile

`HUMAN_TEST_PATCHES` in `build_human_test_disc.py` aggregates six reviewed
groups:

- `BOOT_MENU_PATCHES`;
- `STARTUP_V2_EXTRA_PATCHES`;
- `MISSION_TITLE_PATCHES`; and
- `MISSION0_DIALOGUE_PATCHES`;
- `MISSION0_PROLOGUE_PATCHES`; and
- `INFORMATION_SCREEN_TEXT_PATCHES`.

Every entry contains:

- a payload offset;
- exact expected Japanese text;
- printable ASCII English;
- a purpose label; and
- an optional fixed-cell `wrap_width`.

Printable ASCII is converted to fullwidth Shift-JIS. Short wording is padded
with fullwidth spaces. ASCII hyphen and apostrophe use the encodable Shift-JIS
minus and right-quotation glyphs. When `wrap_width` is set, the formatter pads
non-final lines so the engine's existing cell wrap falls between words. Longer
wording or a single word wider than the configured line is rejected.

`MISSION0_RENDERER_PATCHES` contains the two exact-byte code patches. Do not
change their offsets or replacement bytes without disassembling the source
again and adding a focused test. The builder rejects an image if either
expected byte sequence differs.

`INFORMATION_SCREEN_LINES` keeps each Media Mix row command, source string,
English replacement, semantic purpose, and target row in one record.
`INFORMATION_SCREEN_LAYOUT_PATCHES` is derived from those records rather than
maintained separately. This prevents translation edits from silently drifting
away from their documented layout.

Do not replace a complete dialogue record merely because its visible text fits.
Dialogue controls remain opaque. A new patch must target a confirmed visible
run that is independently bounded from every control and accompanied by a
manual test case.

## Distribution boundary

The output contains copyrighted game data and must stay local. Do not commit or
publish the CCD, IMG, SUB, BIOS, or complete build directory.

A later public release should distribute a patch generated against the
hash-identified source, not this modified image.
