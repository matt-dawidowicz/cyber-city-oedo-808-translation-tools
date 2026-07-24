# Architecture and extension guide

## Design goals

The toolkit is intentionally a set of small command-line programs rather than a
single opaque application. Each stage writes an inspectable file, and later
stages consume only documented columns. This makes false positives, coordinate
mistakes, and heuristic changes easier to audit.

Core principles:

1. preserve the source image;
2. name every coordinate system;
3. separate confirmed format facts from heuristics;
4. retain raw evidence next to decoded text;
5. distinguish discovery confidence from reachability and patch safety;
6. keep exploratory hypotheses out of the canonical pipeline; and
7. fail on structural damage instead of silently producing partial output.

## Module responsibilities

### Confirmed shared model

`game_layout.py` owns title-specific geometry, bank ranges, the observed record
marker, and common opaque control values.

It must not accumulate speculative meanings. A constant belongs there only when
it is used by more than one tool and supported by disc or runtime evidence.

### Lossless extraction boundary

`extract_track2_mode1.py` transforms raw-sector coordinates into payload
coordinates. All later tools operate exclusively on payload bytes.

This boundary prevents scanners from repeatedly reimplementing `2352`-byte
sector math and accidentally treating EDC/ECC bytes as game data.

### Broad discovery

`scan_track.py` and `scan_likely_sjis.py` find structures worth inspecting.
Their outputs are intentionally over-inclusive.

Broad scanners should:

- expose thresholds as arguments when useful;
- write address and evidence columns;
- document false-positive modes; and
- never label a candidate as safe to patch.

### Format-aware extraction

`extract_dialogue.py` implements the strongest current record model. It retains:

- marker address;
- marker and terminator in raw/length evidence;
- decoded glyphs;
- control order;
- raw bytes;
- mission grouping; and
- a conservative confidence label.

If runtime tracing changes the record model, update its tests and format
documentation before regenerating the inventory.

### Set subtraction and presentation

`extract_auxiliary_text.py` removes intervals already owned by structured
dialogue. `build_translation_inventory.py` presents both sources in one schema.

This design avoids double-counting the same dialogue as broad Shift-JIS while
keeping the original stage outputs available for audit.

### Validation

`validate_translation_inventory.py` checks the editable artifact without
rewriting it. Validation rules are separated from generation so translators can
run them after any editor or spreadsheet.

### Visual diagnostics

`render_pce_tiles.py` and `make_contact_sheet.py` are independent from text
extraction. They share the payload coordinate model but make no claim that an
offset is a font or tile bank.

## Evidence levels

Use these labels in future notes and code comments:

### Confirmed from bytes

Examples:

- raw sector sync/mode;
- Shift-JIS decode;
- null terminator;
- exact record offset;
- exact repeated anchor.

### Confirmed from code path

Examples:

- boot code calls `$E060`;
- a parser branch treats a byte as a command;
- a pointer is module-relative.

### Confirmed at runtime

Examples:

- `40` starts a new page;
- a record is reachable;
- a line has a specific pixel width;
- a region is copied before display.

### Heuristic

Examples:

- a Shift-JIS run resembles natural language;
- a sector-aligned uppercase string is a resource header;
- a constant-fill tail is padding.

### Hypothesis

Examples:

- a particular tail is available for relocation;
- a byte could serve as a Latin escape;
- a pointer table has an inferred entry size.

Do not promote a heuristic or hypothesis by changing its variable name alone.
Add the supporting code/runtime evidence.

## Adding a new scanner

1. Decide whether it consumes the raw IMG or extracted payload. Prefer the
   payload unless raw-sector metadata is the subject.
2. Import address constants from `game_layout.py`.
3. Put a complete statement of assumptions and false positives in the module
   docstring.
4. Give every CLI argument useful `--help` text.
5. Write stable TSV headers even for zero results.
6. Include offsets, lengths, and raw evidence needed to reproduce a candidate.
7. Add a synthetic unit test for the parsing rule.
8. Mark the output canonical or exploratory in both its docstring and
   `tool_reference.md`.
9. Compare a regenerated inventory against the prior one.

## Changing the dialogue parser

Before accepting a parser change:

1. Add a synthetic record that demonstrates the new behavior.
2. Retain an invalid example that must still be rejected.
3. Regenerate `dialogue.tsv`.
4. Compare:
   - total records;
   - `likely_text`/`review` counts;
   - bank counts;
   - unique tagged text count;
   - every added/removed offset.
5. Manually inspect raw bytes for a sample of differences.
6. Update `text_format.md`.
7. Generate a new inventory filename and migrate translations deliberately.

A larger record count is not inherently an improvement.

## TSV compatibility contract

Downstream tools identify columns by name, not position. New informational
columns can be added carefully, but renaming or changing the meaning of an
existing column is a schema change.

For schema changes:

- update every reader;
- update `OUTPUT_FIELDS`;
- update the validator;
- update documentation;
- add a migration note;
- regenerate to a new file; and
- do not overwrite a translator's master inventory.

## Future package structure

The current flat scripts keep invocation simple during investigation. Convert
to an installable package only when shared code grows beyond `game_layout.py`
and a few helpers.

A likely later structure:

```text
cyber_oedo/
|-- layout.py
|-- mode1.py
|-- text/
|   |-- codec.py
|   |-- records.py
|   |-- inventory.py
|   `-- validation.py
|-- resources/
|   |-- headers.py
|   `-- pointers.py
`-- patch/
    |-- reinserter.py
    |-- edc_ecc.py
    `-- verify.py
```

Do not create `patch/` until a byte-for-byte no-op rebuild and raw-sector
verification are available.

## Testing strategy

### Synthetic unit tests

Fast and redistributable:

- bank boundary/address math;
- Shift-JIS/control parsing;
- invalid/unterminated record rejection;
- interval merging;
- resource-name filtering;
- 4bpp bitplane order;
- raw Mode 1 payload extraction.

### Golden inventory checks

Local only because they depend on the disc:

- expected payload hash;
- expected total record counts;
- selected known offsets and decoded text;
- no records crossing detected resource boundaries unexpectedly;
- deterministic TSV output.

### Runtime tests

Required for behavior:

- control semantics;
- renderer widths and page flow;
- pointer updates;
- relocation;
- EDC/ECC rebuilt image;
- save/load and audio-track transitions.

## Review checklist

For any code change:

- [ ] Source disc remains unmodified.
- [ ] Coordinate system is explicit.
- [ ] Confirmed facts and heuristics remain separate.
- [ ] `--help` explains inputs and outputs.
- [ ] Empty outputs do not crash.
- [ ] Synthetic tests cover the changed rule.
- [ ] `py_compile` passes.
- [ ] Inventory differences are explained.
- [ ] Documentation matches actual CLI behavior.
- [ ] No reinsertion safety is claimed without runtime/raw-sector proof.
