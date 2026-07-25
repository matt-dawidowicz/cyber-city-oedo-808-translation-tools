# Validation results

Validation date: 2026-07-24

These results describe the documented toolkit in this directory. They separate
code/tool validation from emulator or hardware validation.

## Source and extraction

`extract_track2_mode1.py` was run against the supplied IMG with its title-
specific defaults:

```text
bytes=84375552
sectors=41199
sha256=0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223
```

The result matches the previously extracted payload byte-for-byte by hash.

This validates:

- the selected raw-sector range;
- sync/mode checks;
- user-data slicing; and
- deterministic output identity.

The extractor itself does not validate source EDC/ECC mathematically. The
human-test builder now validates and rebuilds the affected raw sectors through
`cdrom_mode1.py`.

Live hashing also corrected a transcription error in the earlier CCD hash. The
confirmed descriptor SHA-256 is:

```text
716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
```

## Synthetic tests

Command:

```powershell
python -m unittest discover -s .\tests -v
```

Result:

```text
Ran 18 tests
OK
```

Covered behavior:

- half-open mission bank boundaries;
- payload/LBA coordinate helpers;
- Shift-JIS plus opaque control tokenization;
- unterminated-record rejection;
- invalid dialogue-parser bound rejection;
- overlap/adjacency interval merging;
- resource-name versus fill filtering;
- PCE 4bpp plane order; and
- structurally valid Mode 1 user-data extraction;
- standard CD-ROM EDC check vector;
- Mode 1 stale-integrity detection and repair;
- guarded cross-sector payload patching;
- fullwidth startup-profile capacity and expected sector set;
- rejection of low/control characters in profile English;
- docstrings on every module, class, and function;
- PEP 257 summary shape;
- PEP 8's 79-character Python line limit; and
- conventional explanatory-comment prefixes.

## Script loading and CLI documentation

Every Python source file, including the tests, passed `py_compile`.

Every command-line script returned success for `--help`:

- `analyze_text_slots.py`
- `build_human_test_disc.py`
- `build_translation_inventory.py`
- `extract_auxiliary_text.py`
- `extract_dialogue.py`
- `extract_track2_mode1.py`
- `make_contact_sheet.py`
- `render_pce_tiles.py`
- `scan_likely_sjis.py`
- `scan_reversed_sjis.py`
- `scan_track.py`
- `validate_translation_inventory.py`

The two PNG tools were also exercised against the real payload, including a
contact-sheet output located inside its input directory.

## Playable human-test builds

### v0.1 startup profile

`build_human_test_disc.py` completed the historical `boot-menu-v1` profile
against the authenticated CloneCD set:

```text
text_patches=23
changed_relative_sectors=3,4
changed_absolute_lbas=3593,3594
structural_validation=passed
human_emulator_test=pending
```

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  98352b629bb6a7679a56a6f38ff773d100d53c2ca93f9917a764178a7eaf0b17
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

The final IMG is 587,614,272 bytes, equal to the source size. The builder
compared all 249,836 raw sectors and found differences only at the expected
LBAs. Independent post-build checks confirmed:

- the source files retained their original hashes;
- output CCD and SUB hashes equal their source hashes;
- the output IMG has the manifest hash above;
- source text matched at all 23 addresses;
- every replacement preserved Shift-JIS byte length;
- the boundary-crossing missing-file message rebuilt both sectors; and
- stored EDC/ECC matches regeneration for LBAs 3593 and 3594.

An independent byte-range audit found 662 changed raw bytes at LBA 3593 and
270 at LBA 3594. Every difference was either an intended text byte or part of
the EDC/ECC area. Both raw headers and all unrelated user-data bytes remained
identical to the source.

### v0.2 Mission 0 profile

The expanded `mission0-v2` profile completed against the same authenticated
source:

```text
text_patches=58
changed_relative_sectors=3,4,651,6692,12163,17624,22100,26313,30340,34079,36786,37030,37036
changed_absolute_lbas=3593,3594,4241,10282,15753,21214,25690,29903,33930,37669,40376,40620,40626
structural_validation=passed
human_emulator_test=pending
```

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  8f74fe8e1249acc6eb7f574630b63cc009d89c34a5a5f26733898321289ce5fe
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

The final IMG remains 587,614,272 bytes. The builder compared all 249,836 raw
sectors and found differences at exactly the 13 listed LBAs. An independent
post-build audit confirmed for each changed sector:

- the 16-byte raw header is unchanged;
- every changed user-data byte belongs to one of the 58 reviewed text runs;
- no title or dialogue control byte belongs to a replacement range;
- stored EDC/ECC matches regeneration;
- CCD and SUB remain byte-identical to the source; and
- v0.1 remains available as a separate, unchanged build set.

The user reported that the earlier build mostly works. No emulator version,
BIOS hash, complete save/load result, or audio test matrix has been recorded.
Those runtime checks, plus visible review of the new Mission 0 dialogue and
later mission titles, remain the explicit v0.2 human test gate.

### v0.3 screenshot-identified narration

The `mission0-v3` profile adds the exact narration page identified in a tester
screenshot:

```text
payload_offset=0x00175851
source_characters=37
replacement=I HUNT CYBER CROOKS AND TURN THEM IN.
text_patches=59
changed_relative_sectors=3,4,651,747,6692,12163,17624,22100,26313,30340,34079,36786,37030,37036
changed_absolute_lbas=3593,3594,4241,4337,10282,15753,21214,25690,29903,33930,37669,40376,40620,40626
structural_validation=passed
human_emulator_test=pending
```

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  992d4a196d4eb7e853f6a87dd2261c68648f584784368ffe19ef9bdf41f0c597
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

The new 74-byte visible run occupies relative payload sector 747, absolute LBA
4337. The replacement uses the full 37-character capacity. Independent audit
of that raw sector found:

- no changed header bytes;
- no changed user-data bytes outside the selected run;
- 56 differing user-data bytes, with unchanged bytes arising where encoded
  source and replacement bytes already matched;
- valid regenerated Mode 1 EDC/ECC; and
- untouched `0x40` page controls immediately before and after the run.

The complete v0.3 builder again compared all 249,836 raw sectors and accepted
exactly the 14 expected changed LBAs. Visible emulator confirmation of this page
remains pending.

### v0.4 complete opening narration

The `mission0-v4` profile expands the screenshot-identified page to all ten
pages of the same opening record:

```text
text_patches=68
prologue_pages=10
changed_relative_sectors=3,4,651,747,6692,12163,17624,22100,26313,30340,34079,36786,37030,37036
changed_absolute_lbas=3593,3594,4241,4337,10282,15753,21214,25690,29903,33930,37669,40376,40620,40626
structural_validation=passed
human_emulator_test=pending
```

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  cbf2d12f6eadc1b96a71549c27f1a79112b495f162343f6c89b4cca5e2419c4c
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

All ten visible runs remain within relative sector 747, absolute LBA 4337.
Independent comparison of that sector found:

- 816 changed raw bytes;
- 536 changed user-data bytes, all inside reviewed narration runs;
- no changed raw-header or unrelated user-data bytes;
- the original `27 28` record marker;
- all nine original `0x40` page controls;
- the original null terminator; and
- valid regenerated Mode 1 EDC/ECC.

The complete v0.4 builder compared all 249,836 sectors and accepted exactly the
same 14-LBA set as v0.3 because the nine additional pages share LBA 4337. Human
testing must now confirm all ten pages display in order without clipping,
paging regressions, or stale Japanese.

### v0.5 failed 13-cell wrapping experiment

The `mission0-v5` profile keeps the same 68 translated runs and adds
presentation behavior at build time:

- Mission 0 dialogue uses fullwidth lowercase Shift-JIS glyphs;
- narration words are packed into lines no wider than 13 cells;
- non-final short lines are padded to the next automatic wrap boundary;
- no newline or dialogue-control byte is inserted; and
- words wider than the configured line are rejected.

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  6e48fc1b408df70dd997bdc7d0b43786da05869ed207b5761317bfddbcc93e92
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

The changed sector set remains the same 14 LBAs as v0.4. Independent audit of
the narration sector at LBA 4337 found:

- 827 changed raw bytes;
- 548 changed user-data bytes, all inside reviewed narration runs;
- no changed raw-header or unrelated user-data bytes;
- the original `27 28` record marker;
- all nine original `0x40` page controls;
- the original null terminator; and
- valid regenerated Mode 1 EDC/ECC.

Runtime testing rejected the screenshot-derived 13-cell assumption. The game
displayed the padding as bad spacing, still split words, and placed a comma on
its own line. v0.5 remains preserved as evidence, but must not be used as the
base for further translation builds.

Static disassembly subsequently identified the cause:

- the active Mission 0 glyph routine begins at CPU `$5915`;
- `$5946` returns 11 for ordinary glyphs and 12 for listed punctuation;
- the original table includes `81 41` and `81 42`, the Japanese comma/stop;
- fullwidth English comma/period are `81 43` and `81 44`; and
- those English codes therefore took the ordinary 11-cell wrap path.

### v0.6 code-confirmed wrapping and English punctuation

The `mission0-v6` profile changes narration wrapping from 13 to 11 cells and
adds two exact-byte renderer patches:

- payload `0x00137165`: redirect the ordinary-limit return to a code cave;
- payload `0x00136D0E`: recognize `81 43` and `81 44`, returning the original
  12-cell hanging-punctuation limit only for those two codes.

The code cave resides in a 34-byte zero-fill run in the same mapped 8 KiB CPU
page. No original Japanese punctuation entry is replaced. The builder checks
all expected source bytes before applying either patch.

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  2045e3dd606d5e28065acd81ac35d431e5eed71fcd21465f595886bf3a384644
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

The complete v0.6 build accepted exactly 16 changed absolute LBAs:

```text
3593, 3594, 4211, 4212, 4241, 4337, 10282, 15753,
21214, 25690, 29903, 33930, 37669, 40376, 40620, 40626
```

The synthetic suite now has 26 passing tests, including HuC6280 opcode-table
coverage, address formatting, wrap behavior, and guarded renderer-patch
structure. Human testing remains required to confirm the 11-cell layout and
English punctuation on screen. Increasing visible letters per line remains
outside this build because the renderer still advances one 16x16 cell per
glyph.

### v0.7 Media Mix translation and row reflow

The `mission0-v7` profile preserves every v0.6 patch and adds all 43 text
records belonging to the video, novel, and music Media Mix pages. Raw-byte
inspection confirmed that each line begins immediately after a `00 01 RR`
command. The source body uses consecutive 8-pixel tile rows for 16-pixel BIOS
glyphs, explaining the overlap visible in the tester screenshots.

The implementation:

- replaces all 43 records with same-size fullwidth Shift-JIS;
- places visible English at least two tile rows apart;
- reuses original 30-character decorative records for long English titles;
- moves cleared Japanese and decorative fragments to offscreen row `1E`;
- changes 33 row operands while preserving every `00 01` opcode;
- preserves every null terminator, page boundary, and file size; and
- retains the two v0.6 Mission 0 renderer patches unchanged.

The authenticated complete build applied 111 text patches and 35 binary
patches. It accepted exactly 18 changed absolute LBAs:

```text
3593, 3594, 3602, 3603, 4211, 4212, 4241, 4337, 10282, 15753,
21214, 25690, 29903, 33930, 37669, 40376, 40620, 40626
```

Output identity:

```text
CCD  716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b
IMG  1cdb81d72e77ab9bffb3bbbf225a3f976fff1fc598621317d50f621f208a25e9
SUB  ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411
```

An independent post-build decoder re-read all 43 text records and row
commands from the raw output IMG, including the record crossing the payload
sector 12/13 boundary. All replacements and display rows matched. The suite
now has 29 passing tests. Human emulator screenshots remain required to
confirm the page interpreter accepts offscreen row `1E` and that the proposed
English wording is visually centered.

### v0.8 optional opening-title graphic

The `mission0-v8` profile preserves all 111 v0.7 text patches and all 35
renderer/layout patches. It adds one independently selectable cosmetic patch:

- `--title-screen clean` generates a 30,720-byte, 256-by-240 tile image;
- `--title-screen original` omits the patch and never reads the title block;
- the original block at payload `0x0000A000` has SHA-256
  `74319e81bfeba32b385620a8bf32848e78da19271c87b6337decf4991a2fe5c4`;
- the deterministic animation-logo-inspired block has SHA-256
  `c9b0127e5d82834062c909db7f2285e24d6bde959b505bcffbf539bd4baa9593`;
  and
- its translated subtitle is exactly `ATTRIBUTE OF THE BEAST`.

The codec round-trips all 960 generated tiles to the exact row-major source
pixels. The standalone test suite has 36 passing tests, including tile
encoding, title-layout identity, opt-out behavior, the 15-sector guard span,
and cross-sector payload reading.

The approved 1448-by-1086 master and embedded mask independently generated the
same title asset hash. The conversion proportionally fits the source to
256-by-192, centers it in the 256-by-240 frame, and applies luminance threshold
48. This preserves the supplied composition while avoiding a build-time image
dependency.

Both complete authenticated variants built successfully. Original-title mode
retained the exact v0.7 IMG identity:

```text
original title IMG
1cdb81d72e77ab9bffb3bbbf225a3f976fff1fc598621317d50f621f208a25e9

clean title IMG
830b9155e2066621672973bf6bf7378c488f7b90b04e96f0be7691e1d2628d63
```

Original mode changed the same 18 absolute LBAs as v0.7. Clean mode changed 31:

```text
3593, 3594, 3602, 3603, 3610, 3611, 3612, 3613, 3614, 3615,
3616, 3617, 3618, 3619, 3620, 3621, 3622, 4211, 4212, 4241,
4337, 10282, 15753, 21214, 25690, 29903, 33930, 37669, 40376,
40620, 40626
```

The clean patch guards relative sectors 20-34 and changes sectors 20-32. Its
proportional fit leaves the final 32 pixel rows black, matching the source in
sectors 33 and 34. The verifier and manifest distinguish guarded sectors from
actually changed sectors. CCD and SUB hashes remain identical to the
authenticated source in both variants.

Structural and generated-preview validation passed. Emulator confirmation of
the clean title's live palette, timing, and exact display framing remains the
human test gate.

### v0.9 opening profiles and antialiased title

The `mission0-v9` profile preserves the v0.8 translation and adds:

- 80 modeled dossier fields, each patched in the primary and repeated bank;
- 160 same-size fullwidth text patches across all seven opening profiles;
- 46 guarded `00 0C RR` row edits for names and two-line charges;
- a four-bit title coverage mask whose packed SHA-256 is
  `2d48dae1c9807a4a0d6dbe224ab191834aa40b3e1c4510437d6b20a5224dcbc7`;
- a 30,720-byte title asset with SHA-256
  `f8e91ad827040796ea63a80541e06f71159ca18121b10ab5128347ad6206e8f1`;
  and
- a generated 224-byte grayscale replacement for all seven original title
  palette frames.

The source palette cycle at payload `0x00002848` has SHA-256
`650a61cee3f91e3c4b2a5159feb38800384daa2ad6ba48903f3596417fa1085b`.
The separate portrait palette at `0x00002828` is outside the patch. The
approved master is resized to 256 by 192 and centered; luminance 8 maps to
black, 200 maps to white, and intermediate values retain four-bit coverage.
Coverage is remapped to indexes 6 through 15. Indexes 0 through 5 are black,
hiding residual upper-border pixels that the original title routine leaves
active. All seven generated palette frames are byte-identical grayscale ramps,
so the original color-cycle timing cannot tint antialiased edge indexes.

The standalone suite now has 38 passing tests. New coverage verifies:

- artifact-safe title indexes survive tile encoding and decoding;
- the first six title-palette indexes remain black in all seven frames;
- each palette word has equal red, green, and blue components;
- all seven palette frames are identical;
- all 80 profile fields generate two same-size source-guarded patches;
- every profile's visible rows are unique and at least two tile rows apart;
- every Media Mix page's visible rows increase by at least two in actual
  source-record order, preserving the original top-to-bottom reveal;
- all visible Media Mix body lines use a three-cell margin and one source
  record per line; and
- clean-title mode adds only relative palette sector `5` and title sectors
  `20` through `34` to the v0.9 guarded sector set.

Both authenticated variants completed structural and whole-image validation:

```text
original title IMG
dd7843425d241045c5ae9077b9d5d1060714ed704f06b26fe2c54f04a7dc6239

antialiased title IMG
78248c4f0306d81867b94a722e28e566fe92de333bc217c5368a70e7b4880562
```

Original-title mode changed 23 absolute LBAs:

```text
3593, 3594, 3602, 3603, 3655, 3656, 3657, 3783, 3784, 4211,
4212, 4241, 4337, 10282, 15753, 21214, 25690, 29903, 33930,
37669, 40376, 40620, 40626
```

Clean-title mode additionally changed LBA `3595` and LBAs `3610` through
`3622`, for 37 changed sectors and 39 guarded sectors. CCD and SUB hashes
remain byte-identical to the authenticated source in both variants. Emulator
screenshots of all seven profiles and the live antialiased title remain the
manual release gate.

## Dialogue regeneration

The documented `extract_dialogue.py` reproduced:

```text
records=3799
unique_tagged_texts=2429
sjis_characters=92987
likely_text=3721
review=78
MISSION_0=558
MISSION_1=576
MISSION_2=516
MISSION_3=420
MISSION_4=322
MISSION_5=340
MISSION_6=320
MISSION_7=235
MISSION_8=512
ENDING=0
```

The per-bank counts above include both `likely_text` and `review`.

## Broad-scan baseline difference

A clean rerun of the documented broad Shift-JIS scanner produced 2,464
candidates. The older saved `scan/likely_shift_jis.tsv` contains 2,180.

Comparison shows:

- every old broad-scan offset is still present;
- 284 candidates are newly present;
- all 284 lie in the `0x02xxxxxx` payload-offset region;
- 164 of them overlap structured dialogue and are removed by the auxiliary
  subtraction stage; and
- 120 remain as additional auxiliary candidates.

This pattern indicates that the older saved broad-scan artifact omitted part of
one payload region; it is not a behavior change caused by the documented
plausibility thresholds. The clean rerun produced:

```text
auxiliary occurrences=1445
auxiliary unique texts=702
combined occurrences=5244
combined canonical texts=3058
combined review occurrences=244
```

The previously published translator inventory remains a valid 5,124-row
baseline and passes the new structural validator with zero errors. It was not
silently overwritten during this documentation pass. Before translation work
begins, choose one baseline explicitly:

- preserve the 5,124-row inventory for continuity; or
- review the 120 additional auxiliary candidates and promote the 5,244-row
  clean regeneration.

The main structured dialogue inventory is unaffected.

## Inventory validation

Older saved inventory:

```text
rows=5124
canonical_ids=3026
warnings=0
errors=0
```

Clean regeneration:

```text
rows=5244
canonical_ids=3058
warnings=0
errors=0
```

Both currently have blank translation columns.

## Resource-region analysis

The header-bounded analyzer produced:

```text
resource_headers=443
text_regions=364
unassigned_records=0
bounded_text_regions=349
wide_header_gaps=15
records_crossing_regions=0
likely_padded_tails=48
```

The 15 gaps above 64 sectors are explicitly labeled `wide_header_gap` and
cannot produce a positive padding candidate by default. This prevents a missing
intermediate header from being presented as confident relocation space.

No dialogue record crossed its assigned candidate region boundary in this run.

## Not validated

- emulator boot;
- runtime control semantics;
- player-visible coverage;
- exact resource pointers/lengths;
- compact-width English glyph rendering;
- dialogue reinsertion or relocation;
- full-game playthrough.

The startup test image proves same-size fullwidth insertion and raw-sector
rebuilding only. Those remaining milestones are not implied successes.
