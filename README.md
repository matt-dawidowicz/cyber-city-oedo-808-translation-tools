# Cyber City Oedo 808 translation-analysis toolkit

This directory contains a reproducible, read-only analysis pipeline for the
Japanese PC Engine CD release of *Cyber City Oedo 808: Kemono no Alignment*.
It extracts the data track from the supplied CloneCD image, inventories the
disc, finds Shift-JIS text, separates structured dialogue from auxiliary text,
and builds a translator-facing TSV.

The current tools **do not create a patched disc**. That boundary is deliberate:
the text renderer, control-byte semantics, pointers/lengths, and raw Mode 1
EDC/ECC rebuild path must be confirmed before automated reinsertion can be
considered safe.

Start with:

- [Disc layout and address math](docs/disc_layout.md)
- [Data and rights policy](docs/data_policy.md)
- [Text format and TSV schemas](docs/text_format.md)
- [Translation and patch-development workflow](docs/translation_workflow.md)
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
- Repeated engine/resource anchors divide the payload into mission analysis
  banks recorded in `game_layout.py`.

## What is not yet confirmed

- The runtime meaning of dialogue controls `21`, `2F`, `40`, and `5C`.
- Which extracted records are reachable and visible during normal play.
- Every module's pointer and length fields.
- A compact English rendering path.
- Which constant-fill tails are genuinely unreferenced relocation space.
- A correct raw-sector EDC/ECC rebuild and tested CloneCD patch.

The tools preserve those unknowns instead of assigning plausible-sounding names
to them.

## Safety model

The supplied `.ccd`, `.img`, and `.sub` files are source evidence. Every command
here reads them or reads derived files and writes new artifacts elsewhere.

Do not hex-edit the original IMG. A future patching workflow should:

1. work on a copy;
2. patch 2048-byte user data through a format-aware reinserter;
3. recalculate raw-sector EDC/ECC;
4. preserve track starts, pregaps, audio data, and subchannel data; and
5. verify the result in an emulator before any hardware test.

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
See [Data and rights policy](docs/data_policy.md) before contributing or making
the repository public.

## Requirements

- Python 3.11 or newer
- Pillow 10 or newer, only for the PNG tile tools

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
|-- extract_track2_mode1.py          raw IMG -> 2048-byte Track 2 payload
|-- scan_track.py                    sector/ASCII/broad Shift-JIS reconnaissance
|-- scan_likely_sjis.py              natural-language discovery heuristic
|-- extract_dialogue.py              structured 27 28 dialogue records
|-- extract_auxiliary_text.py        broad scan minus dialogue ranges
|-- build_translation_inventory.py   translator-facing occurrence TSV
|-- validate_translation_inventory.py read-only edit/schema checks
|-- analyze_text_slots.py            header-bounded resource-tail analysis
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
    |-- tool_reference.md
    |-- architecture.md
    |-- validation_results.md
    `-- translation_analysis.md
```

`scan_reversed_sjis.py` is intentionally omitted from the canonical path. It is
an exploratory test for reversed two-byte codes, and its own documentation
explains why its output must not enter the translation inventory.

## Project status

This toolkit is ready for reproducible static analysis and translation-script
editing. The next engineering milestone is a runtime trace of the dialogue
renderer and control bytes, followed by a one-line, same-size insertion proof
on a disposable image copy. See
[translation_workflow.md](docs/translation_workflow.md) for the release path.
