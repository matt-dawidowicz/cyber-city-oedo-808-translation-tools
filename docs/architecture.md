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

### Guarded raw-sector patch boundary

`cdrom_mode1.py` owns standard Mode 1 EDC/ECC generation and payload-coordinate
patch application. It must remain game-agnostic and requires exact source bytes
for every same-size replacement.

`build_human_test_disc.py` owns the title-specific trust boundary:

- authenticate the complete source set;
- copy before modification;
- define the limited fullwidth text profile;
- select or omit the generated cosmetic title patch;
- compare all raw sectors;
- preserve CCD and SUB data; and
- write a machine-readable manifest.

`InPlaceTextPatch` owns same-size fullwidth text conversion.
`InformationScreenLine` composes that text rule with the Media Mix
interpreter's adjacent `00 01 RR` row command. It derives both the text patch
and any row-operand patch from one immutable record. Keep those fields together
when editing the merchandise translation; parallel hand-maintained text and
layout tables would allow them to drift.

Do not move source authentication into the low-level sector module. Keeping
those layers separate allows synthetic sector tests without weakening the
release-specific guardrails.

`read_payload_range()` is the one game-agnostic exception needed by large
generated patches. It validates raw sector structure and EDC/ECC while
returning only a requested payload slice. The high-level builder still owns the
release hash, title-block hash, source offset, and interpretation.

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

`pce_graphics.py` is the dependency-free hardware codec shared by visual
diagnostics and generated art. It knows only the 32-byte planar representation
of one tile.

`title_screen.py` owns the optional opening graphic. It generates a complete
256-by-240 palette-index image, encodes its 960 tiles in screen order, and
generates the replacement seven-frame grayscale palette cycle. The generator
reserves indexes 0 through 5 as black and remaps logo coverage into indexes 6
through 15; this hides residual upper-border pixels from the original routine
without disabling its timing. It does not contain original game art, know disc
offsets, or decide whether the patch is enabled. `title_logo_mask.py` stores
only the compressed four-bit coverage mask derived from approved replacement
artwork. These separations allow downstream projects to:

- use the exact approved reference composition;
- import another master image and retain all builder guardrails;
- replace the generator with another same-size asset; or
- select `--title-screen original` and keep every translation patch.

Do not place the source game title block in either module. The builder reads it
and the original 224-byte title palette cycle from the authenticated IMG at
runtime so expected bytes remain exact patch guards without redistributing
game data. The portrait palette immediately before the cycle is deliberately
outside the optional patch.

### Executable-code diagnostics

`disassemble_huc6280.py` owns deterministic single-instruction decoding and
linear presentation. It requires the analyst to supply both the payload/file
offset and logical CPU address because the disc does not encode the runtime
MPR mapping beside each code block.

The disassembler must not decide that bytes are code. Record the evidence for
the module load address separately, and stop a listing before an embedded table
unless the table is itself under investigation. Payload offsets remain the
patch coordinate; logical addresses remain the control-flow coordinate.

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

## Python documentation standard

Every Python module, class, method, nested function, and top-level function
must have a PEP 257-compatible docstring.

Use this structure when a section is relevant:

```text
"""Perform one clearly stated action.

Explain context, assumptions, and non-obvious behavior.

Args:
    name: Meaning, coordinate system, accepted range, or ownership.

Returns:
    Exact return shape and sentinel behavior.

Raises:
    Exceptions intentionally exposed to callers.

Side Effects:
    Files, directories, streams, memory, or external state affected.

Design Decisions:
    Why behavior that may look surprising is intentional.

Notes:
    Limits that do not fit the sections above.
"""
```

Do not add empty sections merely for uniformity. A small pure predicate may
need only `Args`, `Returns`, and a design note; CLI entry points should document
inputs, outputs, side effects, and failure conditions explicitly.

Explanatory comments follow PEP 8:

- use `# ` and complete sentences;
- explain *why* a binary rule, cursor movement, or safety check exists;
- do not narrate obvious assignments or repeat the docstring; and
- keep every Python source line at or below 79 characters.

`tests/test_documentation.py` enforces docstring presence and summary shape,
the 79-character limit, and comment prefixes without third-party lint tools.

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

The flat `cdrom_mode1.py` module supplies the verified rebuild layer, while
`dialogue_relocation.py` supplies a guarded but inactive pointer/page model.
Create a package-level `patch/` only when real resource parsers, activated
relocations, and public patch generation justify that structure.

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
- CD-ROM EDC check vector and Mode 1 ECC regeneration;
- stale-integrity detection and repair;
- guarded cross-sector payload patching;
- fullwidth startup-profile encoding and capacity;
- two-bank opening-profile coverage and non-overlapping row layout;
- four-bit title coverage and stable grayscale palette frames;
- fixed-cell English word wrapping and invalid-input rejection;
- explicit stock-renderer page compilation and added-page opt-in;
- guarded pointer arithmetic and relocation-area containment;
- refusal to relocate without a proven pointer;
- invalid parser-bound validation;
- docstrings on every documentable Python syntax node;
- PEP 257 summary shape; and
- PEP 8 line length and comment prefixes.

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

The local real-disc build adds a middle validation layer:

- source CCD/IMG/SUB hashes;
- source text at every patch coordinate;
- affected original-sector EDC/ECC;
- exact changed raw-sector set;
- unchanged CCD/SUB; and
- output image and sector hashes.

## Review checklist

For any code change:

- [ ] Source disc remains unmodified.
- [ ] Coordinate system is explicit.
- [ ] Confirmed facts and heuristics remain separate.
- [ ] `--help` explains inputs and outputs.
- [ ] Empty outputs do not crash.
- [ ] Synthetic tests cover the changed rule.
- [ ] PEP 257/PEP 8 documentation checks pass.
- [ ] `py_compile` passes.
- [ ] Inventory differences are explained.
- [ ] Documentation matches actual CLI behavior.
- [ ] Reinsertion claims distinguish raw-sector proof from runtime proof.
