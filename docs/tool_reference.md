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
- Source disc files are never modified.

## Recommended command checks

Display authoritative built-in help:

```powershell
python .\extract_dialogue.py --help
python .\analyze_text_slots.py --help
python .\validate_translation_inventory.py --help
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
