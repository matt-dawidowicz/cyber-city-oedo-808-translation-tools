# Cyber City Oedo 808 translation-analysis toolkit

This directory contains a reproducible analysis and test-build pipeline for the
Japanese PC Engine CD release of *Cyber City Oedo 808: Kemono no Alignment*.
It extracts the data track from the supplied CloneCD image, inventories the
disc, finds Shift-JIS text, separates structured dialogue from auxiliary text,
builds a translator-facing TSV, and creates a guarded playable test image.

The current `mission0-stock-renderer` builder creates a **guarded fullwidth
Shift-JIS vertical slice**. It translates startup messages, all mission-title
subtitles,
the opening Mission 0 bartender conversation, and the complete ten-page opening
narration. It translates both copies of all seven opening criminal dossiers
and reflows their overlapping name and charge lines. It also translates and
reflows all three Media Mix merchandise pages. The default build replaces the
original opening art and its seven-frame color cycle with an antialiased
grayscale screen modeled on the animation logo, including the translated
subtitle `ATTRIBUTE OF THE BEAST`. Its low palette indexes remain black so
stray pixels from the original upper-border effect stay hidden;
`--title-screen original` omits only those two cosmetic patches.
Mission 0 uses lowercase English. Narration pages are padded for word-aware
wrapping at the renderer's code-confirmed 11-cell boundary. No parser, glyph,
cursor, or punctuation code is patched. It is not a complete English
translation. Resource access, pointer aliases, loaded extents, and relocation
areas still require runtime proof before broad automated reinsertion is safe.

Start with:

- [Disc layout and address math](docs/disc_layout.md)
- [Data and rights policy](docs/data_policy.md)
- [Text format and TSV schemas](docs/text_format.md)
- [Translation and patch-development workflow](docs/translation_workflow.md)
- [Renderer freeze and relocation strategy](docs/renderer_freeze_and_relocation.md)
- [Playable human-test build](docs/human_test_build.md)
- [Complete command reference](docs/tool_reference.md)
- [Architecture and extension guide](docs/architecture.md)
- [Validated results and known baseline difference](docs/validation_results.md)
- [Original static-analysis report](docs/translation_analysis.md)

## What is confirmed

- Track 2 contains 41,199 valid Mode 1 data sectors.
- The extracted user-data payload is 84,375,552 bytes.
- Its SHA-256 is
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.
- Main dialogue is ordinary null-terminated Shift-JIS.
- Candidate dialogue records begin with bytes `27 28`.
- Low ASCII-range values inside those records are controls, not safe ASCII text.
- The boot code calls the System Card BIOS `EX_GETFNT` routine at `$E060` in
  16x16 glyph mode.
- The active Mission 0 renderer wraps ordinary glyphs at 11 cells and permits
  listed punctuation in a twelfth hanging cell.
- Control `2F` is a skippable 20-vblank delay; `5C` waits for a press/release;
  `21` waits on `$37F1`; and `40` advances the text row after window handling.
- Repeated engine/resource anchors divide the payload into mission analysis
  banks recorded in `game_layout.py`.
- Standard Mode 1 EDC and P/Q ECC rebuilding matches original raw sectors.
- The startup menu accepts same-size fullwidth Shift-JIS English.
- Visible dialogue runs can be replaced without touching adjacent controls.

## What is not yet confirmed

- The runtime meaning of dialogue controls `21`, `2F`, `40`, and `5C`.
- Which extracted records are reachable and visible during normal play.
- Every module's pointer and length fields.
- The access mode and pointer aliases for each dialogue resource.
- Which constant-fill tails are genuinely unreferenced relocation space.
- Emulator boot, save/load, audio continuity, and later track transitions for
  the generated human-test build.

The tools preserve those unknowns instead of assigning plausible-sounding names
to them.

## Safety model

The supplied `.ccd`, `.img`, and `.sub` files are source evidence. Analysis
commands read them or derived files. The test builder authenticates the source,
copies the complete set to an isolated output directory, and patches only the
copy.

Do not hex-edit the original IMG. `build_human_test_disc.py` now performs the
limited proof workflow:

1. work on a copy;
2. patch same-size 2048-byte user data through a guarded reinserter;
3. recalculate raw-sector EDC/ECC;
4. preserve track starts, pregaps, audio data, and subchannel data; and
5. leave emulator confirmation as the required human test gate.

The builder rejects unknown source hashes, mismatched source text, changed file
sizes, stale EDC/ECC, unexpected modified sectors, and altered CCD/SUB data.

## Repository contents and data policy

This project repository contains original analysis code, documentation, and
synthetic tests. It intentionally does not contain:

- CloneCD `.ccd`, `.img`, or `.sub` files;
- ISO/CHD/CUE/BIN disc images;
- the extracted 84 MB Track 2 payload;
- full generated dialogue, auxiliary-text, or translation TSVs;
- audio tracks, screenshots, tile dumps, or renders; or
- emulator BIOS files.

You must supply your own legally obtained source image and generate local
artifacts with the documented commands. `.gitignore` enforces these boundaries.
The clean title is a compact four-bit coverage mask derived from approved
replacement artwork, not an extracted game graphic. Its guarded source graphic
and seven-frame palette bytes are read from the authenticated IMG during a
build and are never stored in the repository. The portrait palette immediately
before the title cycle remains untouched. Coverage is remapped into palette
indexes 6 through 15; indexes 0 through 5 remain black to suppress residual
upper-border pixels drawn by the original title routine.
See [Data and rights policy](docs/data_policy.md) before contributing or making
the repository public.

## Requirements

- Python 3.11 or newer
- Pillow 10 or newer, only for PNG tools and optional title-image importing

Install the optional image dependency:

```powershell
python -m pip install -r requirements.txt
```

The extraction, scanning, TSV, and validation tools otherwise use only the
Python standard library.

## Reproduce the inventory

Run these commands from this directory. Quote paths because the disc filename
contains spaces.

### 1. Extract the Mode 1 user-data payload

```powershell
python .\extract_track2_mode1.py `
  "C:\path\to\Cyber City Oedo 808 - Kemono no Alignment (Japan).img" `
  .\track02_mode1_2048.bin
```

Expected identity:

```text
bytes=84375552
sectors=41199
sha256=0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223
```

The extractor validates raw-sector sync and the Mode 1 byte. It does not claim
to authenticate EDC/ECC.

### 2. Build the structural reconnaissance files

```powershell
python .\scan_track.py .\track02_mode1_2048.bin --output-dir .\scan
python .\scan_likely_sjis.py `
  .\track02_mode1_2048.bin `
  .\scan\likely_shift_jis.tsv
```

### 3. Extract structured dialogue

```powershell
python .\extract_dialogue.py `
  .\track02_mode1_2048.bin `
  .\dialogue.tsv
```

`dialogue.tsv` retains the marker, null terminator, raw bytes, byte length,
controls, tagged text, visible text, and payload address for every candidate.

### 4. Isolate auxiliary text

```powershell
python .\extract_auxiliary_text.py `
  .\scan\likely_shift_jis.tsv `
  .\dialogue.tsv `
  .\auxiliary_text.tsv
```

This subtracts every dialogue byte range from the broad text scan. The result
contains UI labels, item/location/system text, and heuristic review candidates.

### 5. Build the editable occurrence inventory

```powershell
python .\build_translation_inventory.py `
  .\dialogue.tsv `
  .\auxiliary_text.tsv `
  .\translation_inventory.tsv
```

The inventory has one row per binary occurrence. Repeated visible strings share
a `canonical_id`; their locations remain separate.

### 6. Validate the generated or translator-edited TSV

```powershell
python .\validate_translation_inventory.py .\translation_inventory.tsv
```

To fail while any translation cell remains blank:

```powershell
python .\validate_translation_inventory.py `
  .\translation_inventory.tsv `
  --require-translations
```

The validator never rewrites the file.

### 7. Analyze named resource tails

```powershell
python .\analyze_text_slots.py `
  .\track02_mode1_2048.bin `
  .\dialogue.tsv `
  .\scan\ascii_strings.tsv `
  .\text_regions.tsv
```

Despite its historical filename, this tool does not assume fixed four-sector
slots. It discovers sector-aligned resource names and measures each region up
to the next name. A `tail_is_likely_padding=yes` result is evidence for pointer
research, not permission to overwrite the tail. Gaps over 64 sectors are marked
`wide_header_gap` and cannot produce a positive padding result by default.

## Editing the translation inventory

Routine translator edits belong only in:

- `english_translation`
- `translator_notes`

Treat every other column as generated analysis data.

Important rules:

1. Do not type English directly over the Japanese bytes in the IMG. Ordinary
   ASCII values collide with the game's control-byte range.
2. Do not delete or reinterpret `controls` or `tagged_source`.
3. Translate naturally for visible context; do not force English to match the
   source character count at this stage.
4. Use `canonical_id` to find repeated wording, but inspect each occurrence's
   `bank`, `kind`, and control layout before reusing a translation.
5. Put uncertainty, speaker/context notes, and required screenshots in
   `translator_notes`.
6. Keep the file tab-separated and UTF-8. The generated BOM helps spreadsheet
   programs recognize Japanese text.
7. Run `validate_translation_inventory.py` after saving from a spreadsheet.

`english_translation` currently contains visible English only. Control placement
will become a separate insertion concern after runtime tracing gives each
control a verified meaning. Do not invent a tagged-English syntax prematurely.

## Build the playable human-test image

The stock-renderer vertical slice translates 271 visible runs with the original
16x16 fullwidth glyph path, applies no dialogue code patches, and repositions
80 row operands. By default it also generates replacements for the opening
256-by-240 tile graphic and its isolated seven-frame palette cycle:

- 23 original startup notice, menu, load, and memory runs;
- 11 additional memory-state and recovery messages;
- 10 mission-title subtitle occurrences;
- 14 visible segments in the opening Mission 0 bartender exchange; and
- all 10 pages of Sengoku's opening narration;
- 160 fields covering both copies of all seven opening dossiers; and
- 43 records across the video, novel, and music Media Mix pages.

```powershell
python .\build_human_test_disc.py `
  "C:\path\to\Cyber City Oedo 808 - Kemono no Alignment (Japan).ccd" `
  "C:\path\to\output\cyber_city_oedo_808_stock_renderer"
```

The output directory must not already exist. Open the generated `.ccd` in a PC
Engine CD emulator with a legally obtained Japanese System Card 3.0 BIOS.

To build the same translation while preserving the original opening graphic:

```powershell
python .\build_human_test_disc.py `
  "C:\path\to\Cyber City Oedo 808 - Kemono no Alignment (Japan).ccd" `
  "C:\path\to\output\cyber_city_oedo_808_stock_renderer_original" `
  --title-screen original
```

Automated build verification covers:

- exact source CCD/IMG/SUB hashes;
- exact source text at all 271 payload offsets;
- equal-length fullwidth Shift-JIS replacements;
- 46 guarded opening-profile row-operand changes;
- 34 guarded Media Mix row-operand changes;
- Mode 1 EDC and ECC regeneration;
- all-sector comparison proving exactly 21 LBAs change in original-title mode
  or 35 LBAs in clean-title mode;
- an independent SHA-256 guard over the complete original title block;
- an independent SHA-256 guard over the seven original title palettes;
- byte-identical CCD and SUB copies; and
- an output manifest with before/after sector and image hashes.

This is a vertical slice, not a full translation. Dialogue outside the opening
bar exchange and most later interfaces remain Japanese. Follow
[human_test_build.md](docs/human_test_build.md) for the tester checklist and
distribution boundary.

The stock profile retains the stable formatter that prevents words from
crossing the code-confirmed 11-cell narration boundary by padding the prior
line with fullwidth spaces. Punctuation remains inside that ordinary limit.
Accurate longer English uses additional pages and guarded relocation only
after the record's access path and loaded destination ownership are proven.

The Media Mix pages use a separate row-addressed format. Their original
consecutive 8-pixel rows overlap 16-pixel glyphs. The data-only reflow
spaces visible rows two tile rows apart and moves cleared records to offscreen
row `0x1E`; it does not change the shared dialogue renderer. Visible target
rows also increase in source-record order so the original top-to-bottom reveal
animation is preserved. Every visible body line uses the same three-cell left
margin, and each title is deliberately concise enough to remain on one line.

Opening dossiers use a related `00 0C RR` row command. The v0.9 profile clears
the redundant Japanese name line offscreen, moves the existing romanized name
to row `0x04`, and spaces two-line charges, aliases, and bounties two tile rows
apart. It applies the same guarded translation to both dossier banks.

## Graphics reconnaissance

Render 512 candidate tiles beginning at payload offset `0x00145800`:

```powershell
python .\render_pce_tiles.py `
  .\track02_mode1_2048.bin `
  .\renders\00145800.png `
  --offset 0x00145800
```

Combine all renders into a labeled sheet:

```powershell
python .\make_contact_sheet.py `
  .\renders `
  .\renders_contact.png `
  --columns 4
```

The renderer uses grayscale palette indexes. Correct shapes with incorrect
colors are expected because the runtime palette is not reconstructed.

The opening screen is simpler than the later tile reconnaissance suggested:
payload bytes `0x0000A000` through `0x000117FF` are 960 raw tiles already
ordered as a 32-by-30 screen. `title_screen.py` generates a clean replacement
without embedding source art. To edit and preview it independently:

```powershell
python .\title_screen.py .\local_artifacts\clean_title.bin
python .\render_pce_tiles.py `
  .\local_artifacts\clean_title.bin `
  .\local_artifacts\clean_title.png `
  --offset 0 --tiles 960 --tiles-wide 32 --scale 2
```

The default silhouette is stored in `title_logo_mask.py`. To replace it, pass a
new master to `title_screen.py --source-image`; the importer proportionally
fits and centers the image, then maps luminance 8 through 200 to four-bit edge
coverage using the same documented process.
The generator enforces the 256-by-240, four-bit, tile-major hardware format.
Generated `.bin` and `.png` files are local artifacts, not repository content.

## Test after changing code

The tests use synthetic data and source inspection; they do not require the
game image. They also enforce the repository's PEP 257 docstring baseline,
PEP 8 line limit, and explanatory-comment prefix:

```powershell
python -m unittest discover -s .\tests -v
```

Then compile every script:

```powershell
$files = (Get-ChildItem -Filter *.py).FullName
python -m py_compile $files
```

For changes to heuristics, regenerate the inventory and compare record counts,
offsets, and source hashes before accepting the change.

## Directory map

```text
.
|-- README.md
|-- game_layout.py                   confirmed shared constants/address helpers
|-- cdrom_mode1.py                   guarded raw Mode 1 EDC/ECC patch layer
|-- extract_track2_mode1.py          raw IMG -> 2048-byte Track 2 payload
|-- scan_track.py                    sector/ASCII/broad Shift-JIS reconnaissance
|-- scan_likely_sjis.py              natural-language discovery heuristic
|-- extract_dialogue.py              structured 27 28 dialogue records
|-- extract_auxiliary_text.py        broad scan minus dialogue ranges
|-- build_translation_inventory.py   translator-facing occurrence TSV
|-- validate_translation_inventory.py read-only edit/schema checks
|-- analyze_text_slots.py            header-bounded resource-tail analysis
|-- build_human_test_disc.py         authenticated playable test build
|-- pce_graphics.py                  dependency-free PCE 4bpp tile codec
|-- title_screen.py                  generated optional opening-title art
|-- title_logo_mask.py               approved packed replacement silhouette
|-- render_pce_tiles.py              PCE 4bpp diagnostic renderer
|-- make_contact_sheet.py            labeled PNG aggregation
|-- tests/
|   |-- test_documentation.py        PEP 257/PEP 8 source contract
|   `-- test_toolkit.py              synthetic binary-format tests
`-- docs/
    |-- disc_layout.md
    |-- data_policy.md
    |-- text_format.md
    |-- translation_workflow.md
    |-- human_test_build.md
    |-- tool_reference.md
    |-- architecture.md
    |-- validation_results.md
    `-- translation_analysis.md
```

`scan_reversed_sjis.py` is intentionally omitted from the canonical path. It is
an exploratory test for reversed two-byte codes, and its own documentation
explains why its output must not enter the translation inventory.

## Project status

This toolkit is ready for reproducible static analysis, translation-script
editing, and a structurally verified stock-renderer Mission 0 vertical slice.
Initial human testing reports that the earlier startup build mostly works; a
recorded save/load and audio test matrix remains the release gate. Mapping
resource entry modes, pointer aliases, and loaded extents is the next
engineering milestone. See
[translation_workflow.md](docs/translation_workflow.md) for the release path.
