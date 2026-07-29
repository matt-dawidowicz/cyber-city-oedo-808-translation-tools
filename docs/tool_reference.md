# Tool reference

## Canonical pipeline

```text
CloneCD IMG
    |
    v
extract_track2_mode1.py
    |
    +--> track02_mode1_2048.bin
            |
            +--> scan_track.py
            |       +--> summary.txt
            |       +--> sector_map.tsv
            |       +--> ascii_strings.tsv
            |       `--> shift_jis_strings.tsv
            |
            +--> scan_likely_sjis.py --> likely_shift_jis.tsv
            |
            +--> extract_dialogue.py --> dialogue.tsv
                         |
likely_shift_jis.tsv ----+--> extract_auxiliary_text.py --> auxiliary_text.tsv
                                                                  |
dialogue.tsv -----------------------------------------------------+
                                                                  v
                                                build_translation_inventory.py
                                                                  |
                                                                  v
                                                   translation_inventory.tsv
                                                                  |
                                                                  v
                                              validate_translation_inventory.py
```

All sector/offset outputs after extraction use the 2048-byte payload coordinate
system.

The independent human-test build path is:

```text
authenticated CCD + IMG + SUB
              |
              v
build_human_test_disc.py
              |
              +--> copied CCD and SUB
              +--> patched IMG through cdrom_mode1.py
              +--> build_manifest.json
              `--> HUMAN_TEST_README.txt
```

## `game_layout.py`

Purpose: one source of truth for confirmed title-specific constants.

Important exports:

| Name | Meaning |
|---|---|
| `RAW_SECTOR_SIZE` | 2352-byte CloneCD sector |
| `MODE1_USER_DATA_OFFSET` | user data begins at raw byte 16 |
| `SECTOR_SIZE` | 2048-byte extracted sector |
| `TRACK2_START_LBA` | absolute LBA 3590 |
| `TRACK2_SECTOR_COUNT` | 41,199 |
| `DIALOGUE_MARKER` | `27 28` |
| `COMMON_DIALOGUE_CONTROLS` | common values retained as opaque controls |
| `LIKELY_PADDING_BYTES` | fill values used only for heuristic analysis |
| `BANKS` | half-open mission/ending sector ranges |

Use `payload_offset`, `absolute_lba`, `bank_for_sector`, and `bank_for_offset`
instead of open-coding address arithmetic in new tools.

## `cdrom_mode1.py`

Purpose: validate, patch, and rebuild raw 2352-byte Mode 1 sectors.

Important exports:

| Name | Meaning |
|---|---|
| `PayloadPatch` | same-size expected/replacement bytes at a payload offset |
| `compute_edc` | reflected CD-ROM EDC calculation |
| `rebuild_mode1_sector` | regenerate EDC, reserved bytes, and P/Q ECC |
| `mode1_integrity_matches` | compare stored integrity fields to regeneration |
| `apply_payload_patches` | prevalidate and write complete affected sectors |

`apply_payload_patches` accepts replacements that cross payload-sector
boundaries. It validates all affected source sectors and builds every
replacement in memory before its first write.

This module modifies the image path passed to it. Call it only with a disposable
copy. It does not authenticate the complete game release or compare unchanged
sectors; those responsibilities belong to the higher-level builder.

## `extract_track2_mode1.py`

Purpose: convert the relevant raw IMG range to flat 2048-byte Mode 1 user data.

```text
usage: extract_track2_mode1.py [-h] [--start-lba START_LBA]
                              [--sector-count SECTOR_COUNT]
                              image output
```

Arguments:

- `image`: source `.img` with 2352-byte sectors.
- `output`: destination `.bin`.
- `--start-lba`: defaults to 3590.
- `--sector-count`: defaults to 41,199.

Checks:

- input is long enough;
- every selected sector has the Mode 1 sync pattern;
- every selected sector has mode byte `01`;
- output is installed only after all selected sectors pass.

Does not check:

- CCD metadata;
- EDC/ECC validity;
- subchannel data;
- game bootability.

## `build_human_test_disc.py`

Purpose: create the authenticated stock-renderer playable-format test build.

```text
usage: build_human_test_disc.py [-h] [--title-screen {clean,original}]
                                source_ccd output_directory
```

Arguments:

- `source_ccd`: descriptor for the source CloneCD set;
- `output_directory`: new directory for the completed test build;
- `--title-screen clean`: use the antialiased animation-logo-inspired opening
  graphic and its isolated grayscale palette cycle; and
- `--title-screen original`: omit only those two cosmetic patches.

Source requirements:

- CCD, IMG, and SUB companions exist;
- every SHA-256 matches the documented release;
- affected source sectors have valid stored EDC/ECC;
- every selected Japanese text run matches exactly.

Profile behavior:

- converts printable ASCII English to fullwidth Shift-JIS;
- maps ASCII hyphen and apostrophe to encodable Shift-JIS punctuation;
- supports optional word-aware padding for a fixed display-cell width;
- uses the code-confirmed 11-cell width for the opening narration;
- pads shorter wording with fullwidth spaces;
- rejects longer or byte-size-changing wording;
- applies 271 startup, dossier, mission-title, Mission 0, and Media Mix text
  patches;
- applies no dialogue parser or renderer code patches;
- applies 46 guarded dossier row-operand patches for readable spacing;
- applies 34 guarded Media Mix row-operand patches for readable spacing;
- optionally applies one 30,720-byte title-graphic patch and one 224-byte
  seven-frame palette patch;
- preserves all adjacent dialogue and title control bytes;
- changes 21 reviewed sectors in original-title mode or 35 in clean mode; and
- rebuilds EDC/ECC for every guarded Mode 1 sector.

Whole-build verification:

- CCD and SUB output hashes equal the source hashes;
- IMG size is unchanged;
- every output replacement matches;
- all 249,836 raw sectors are compared;
- the changed raw-sector set equals the selected variant's expected LBAs;
- a JSON manifest records source/output/sector hashes, exact text, and exact
  row-command bytes;
- large binary patches use before/after SHA-256 values instead of embedding
  bulky hexadecimal data; and
- the manifest records guarded sectors separately from byte-different sectors.

The output is a limited vertical slice. It translates the opening Mission 0
bartender exchange and complete ten-page narration with lowercase text and
word-aware 11-cell wrapping. It also translates the three Media Mix
merchandise pages and separates their 16-pixel glyphs onto non-overlapping tile
rows. It does not relocate records or provide a compact Latin renderer.

## `dialogue_relocation.py`

Purpose: compile explicit stock-renderer pages and model relocation only after
pointer and destination ownership are proven.

This is a library module, not a disc-writing command.

Key interfaces:

- `PageGeometry` stores record-specific line width, page height, and page
  command.
- `DialoguePage` stores translator-approved visual lines.
- `PageBreakPlan` validates a page-only source record and compiles fullwidth
  Shift-JIS pages without a renderer escape.
- `PointerSite` stores one exact little-endian pointer field and base.
- `RelocationArea` stores exact owned destination bytes inside a proven loaded
  resource.
- `DialogueRelocationPlan` emits a source guard, every pointer update, and one
  same-size destination-area patch.
- `find_u16_pointer_candidates` performs a bounded byte search but does not
  claim that a match is a real pointer.

The module rejects mixed-control source records, silent removal of page breaks,
unapproved added pages, missing pointers, pointer-window overflow, overlap,
out-of-resource destinations, and insufficient capacity. No real relocation is
included in `HUMAN_TEST_PATCHES` or `HUMAN_TEST_BINARY_PATCHES`.

## `disassemble_huc6280.py`

Purpose: linearly decode a caller-confirmed HuC6280 code region while showing
both payload/file offsets and logical CPU addresses.

```text
usage: disassemble_huc6280.py [-h] --offset OFFSET --address ADDRESS
                              --length LENGTH binary
```

Arguments:

- `binary`: extracted payload or module containing the code;
- `--offset`: byte offset of the first opcode;
- `--address`: logical CPU address corresponding to that offset; and
- `--length`: exact byte count to decode.

All numeric options accept decimal or `0x`-prefixed hexadecimal. The tool uses
the complete HuC6280 opcode/addressing matrix and formats relative branches
against the supplied logical address.

This is intentionally a linear disassembler. It does not infer MPR mappings,
follow control flow, or distinguish code from data. Supplying an arbitrary
offset can therefore produce plausible-looking nonsense. Establish the module
load mapping independently and keep both coordinate systems in analysis notes.

## `scan_track.py`

Purpose: broad sector and string reconnaissance.

```text
usage: scan_track.py [-h] --output-dir OUTPUT_DIR
                     [--minimum-ascii N] [--minimum-japanese N]
                     track
```

Outputs:

- `summary.txt`
- `sector_map.tsv`
- `ascii_strings.tsv`
- `shift_jis_strings.tsv`

`sector_map.tsv` fields:

| Field | Meaning |
|---|---|
| `sector` | relative payload sector |
| `offset` | sector-start payload offset |
| `nonzero` | number of bytes not equal to zero |
| `unique` | number of distinct byte values |
| `entropy` | Shannon entropy in bits/byte |
| `prefix_hex` | first 16 bytes |

Entropy is a triage signal, not a data-type detector. Compressed data, audio-like
data, code, graphics, and encrypted data can overlap in entropy.

## `scan_likely_sjis.py`

Purpose: find Shift-JIS-compatible runs that resemble Japanese sentences or
labels.

```text
usage: scan_likely_sjis.py [-h] [--minimum-tokens N] input output
```

The heuristic accepts:

- printable ASCII tokens;
- halfwidth Katakana;
- valid two-byte Shift-JIS.

It then requires one of:

- a sufficiently long sentence with enough Kana;
- a Japanese-heavy label; or
- a fullwidth label with no ASCII.

It rejects highly repetitive candidates and certain ASCII-heavy forms. Tune
these thresholds only with before/after inventory comparisons.

## `extract_dialogue.py`

Purpose: parse marker-based, null-terminated dialogue.

```text
usage: extract_dialogue.py [-h] input output
```

Parser limits:

- maximum 1024 body bytes before a terminator;
- valid standard Shift-JIS lead/trail ranges;
- halfwidth Katakana support;
- low bytes preserved as `<$XX>`;
- unsupported high bytes reject the candidate.

The scanner advances one byte after every found marker, including rejected
candidates, so overlapping forensic candidates are not skipped.

## `extract_auxiliary_text.py`

Purpose: remove all dialogue-overlapping byte ranges from the broad likely-text
scan.

```text
usage: extract_auxiliary_text.py [-h] likely_scan dialogue output
```

All dialogue intervals are merged before overlap testing. A likely-text run is
discarded if any part overlaps a dialogue record.

## `build_translation_inventory.py`

Purpose: merge dialogue and auxiliary text into one occurrence-level TSV.

```text
usage: build_translation_inventory.py [-h] dialogue auxiliary output
```

ID behavior:

- `entry_id` is assigned in payload-offset order.
- `canonical_id` is assigned when a visible source string is first seen.
- `occurrence_count` counts matching visible source text.

IDs are stable only for the same ordered input set. Adding an earlier discovery
can renumber later IDs. Preserve offset/source evidence when migrating edits.

## `validate_translation_inventory.py`

Purpose: detect accidental damage after spreadsheet/manual editing.

```text
usage: validate_translation_inventory.py [-h] [--require-translations]
                                         inventory
```

Errors cause exit code 1:

- missing required column;
- blank or duplicate occurrence ID;
- blank canonical ID;
- malformed or out-of-order offset;
- malformed/non-positive source byte count;
- one canonical ID mapped to multiple source strings;
- one source string split across canonical IDs;
- blank translation with `--require-translations`.

Warnings do not fail:

- multiple non-empty English translations for one canonical ID.

The validator is read-only.

## `analyze_text_slots.py`

Purpose: measure the tail after dialogue inside candidate named resource
regions.

```text
usage: analyze_text_slots.py [-h] [--include-review]
                             [--max-region-sectors N]
                             track dialogue ascii_scan output
```

Historical note: the filename predates the discovery that resources are not
uniform four-sector slots.

Header rule:

- ASCII run begins at within-sector offset zero;
- name is 2-16 uppercase letters/digits/underscores;
- repeated single-character fills are rejected.

Region rule:

- start at one header;
- end at the next discovered header or payload end;
- assign a dialogue record to the closest preceding header.

`tail_is_likely_padding=yes` requires at least 80% of the tail to be one of
`00`, `08`, `E5`, or `FF`. It also requires the gap to the next named header to
be at most `--max-region-sectors` (default 64). Wider gaps are labeled
`wide_header_gap` because an undiscovered boundary is likely. A positive result
is a prioritization signal only.

## `pce_graphics.py`

Purpose: encode and decode one raw PC Engine 8-by-8, four-bit planar tile
without requiring Pillow.

Library functions:

- `encode_tile(pixels)`: convert 64 row-major palette indexes to 32 bytes; and
- `decode_tile(tile)`: convert a 32-byte planar tile to 64 palette indexes.

Both functions reject malformed sizes or palette indexes. The title generator,
diagnostic renderer, and synthetic tests share this codec.

## `title_screen.py`

Purpose: generate the optional clean 256-by-240 opening-title asset.

```text
usage: title_screen.py [-h] [--source-image SOURCE_IMAGE]
                       output
```

The output is exactly 30,720 bytes: 960 tiles in 32-column, 30-row screen
order. The default uses a compressed, SHA-256-guarded four-bit coverage mask
derived from the approved logo reference. `--source-image` instead uses Pillow
to proportionally fit and center another master. Luminance at or below 8 maps
to black, luminance at or above 200 maps to white, and the interval between
them retains four-bit edge coverage.

`build_grayscale_title_palette_cycle()` emits the companion 224-byte palette
replacement. It repeats one 16-index grayscale frame seven times so the
original color-cycle code cannot change antialiased edge colors. Indexes 0
through 5 remain black to hide the original routine's residual upper-border
pixels; title coverage is remapped into indexes 6 through 15. The portrait
palette before the cycle is not part of this replacement.

The command does not read or modify a disc image. It replaces only the
requested standalone output file so contributors can render and inspect
revisions before running the full builder. Normal default generation does not
import or require Pillow.

## `render_pce_tiles.py`

Purpose: decode candidate raw PC Engine 4bpp graphics.

```text
usage: render_pce_tiles.py [-h] --offset OFFSET [--tiles TILES]
                           [--tiles-wide TILES_WIDE] [--scale SCALE]
                           input output
```

- Offset accepts decimal or `0xHEX`.
- One tile is 32 bytes.
- Output indexes use a diagnostic grayscale palette.
- Incomplete final tile bytes are ignored.
- A request that yields no complete tile is an error.

The tool does not decode tilemaps, palettes, sprites, compression, or runtime
VRAM layout.

## `make_contact_sheet.py`

Purpose: combine PNG renders into an address-ordered visual sheet.

```text
usage: make_contact_sheet.py [-h] [--columns COLUMNS] input_dir output
```

All `*.png` files are sorted alphabetically. If the output is in `input_dir`,
that exact file is excluded from future inputs.

## `scan_reversed_sjis.py`

Status: **exploratory, non-canonical**.

Purpose: test binary regions for two-byte Shift-JIS values stored as trail/lead
instead of normal lead/trail order.

```text
usage: scan_reversed_sjis.py [-h] [--minimum N] input output
```

The game's main text was confirmed to use normal Shift-JIS. Do not merge this
output into the translation inventory. A candidate is evidence for inspecting a
specific binary table, nothing more.

## Exit behavior and file creation

- Argument/validation failures use a non-zero exit code.
- Parent directories are created for normal outputs.
- TSV outputs have explicit headers even when no candidates are found.
- Translator-facing TSVs use UTF-8 with a BOM.
- Source disc files are never modified; the test builder modifies only its
  authenticated copy.

## Recommended command checks

Display authoritative built-in help:

```powershell
python .\extract_dialogue.py --help
python .\analyze_text_slots.py --help
python .\validate_translation_inventory.py --help
python .\build_human_test_disc.py --help
```

Run tests:

```powershell
python -m unittest discover -s .\tests -v
```

Compile:

```powershell
$files = (Get-ChildItem -Filter *.py).FullName
python -m py_compile $files
```
