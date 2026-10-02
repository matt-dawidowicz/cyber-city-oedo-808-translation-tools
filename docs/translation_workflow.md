# Translation and patch-development workflow

## Current deliverable boundary

The current deliverable is a reproducible source-text inventory plus documented
analysis tools. It is suitable for:

- script translation;
- terminology and character-voice work;
- runtime coverage planning;
- renderer/control reverse engineering; and
- locating candidate resources and padding.

The repository now contains the first guarded reinsertion path for the final
dialogue master. The packed-English Mission 0 test builder conservatively inserts reviewed
spoken/narration rows only when they map exactly to the authenticated payload
and the packed English exactly fills the existing visible-text footprint.
Shorter padding-dependent rows are classified separately until final-runtime
padding behavior is live-certified. Growth, split/control
records, later-bank renderer activation, and full release QA remain gated.
See `final_dialogue_insertion_status.md`.

## Phase 1: establish a stable source baseline

1. Preserve the original `.ccd`, `.img`, and `.sub`.
2. Record their SHA-256 values from `disc_layout.md`.
3. Extract `track02_mode1_2048.bin`.
4. Verify the expected payload size and SHA-256.
5. Generate every TSV from that payload.
6. Save the exact commands and Python version with the translation project.

Do not compare offsets from two payloads unless their hashes match.

## Phase 2: translate the inventory

Work in `translation_inventory.tsv`.

### Translator-facing rules

- Write natural, complete visible English in `english_translation`.
- Use `translator_notes` for context gaps, speaker identity, alternative
  readings, terminology, screenshot needs, and length risks.
- Preserve every generated column.
- Filter `quality=review` into a separate review pass.
- Use `canonical_id` for consistency, but verify each occurrence's context.
- Do not manually copy `<$XX>` tags into English yet; the tags have no confirmed
  semantics or insertion syntax.

### Suggested review order

1. Mission 0/tutorial and system notices
2. recurring UI labels
3. item/location/person names
4. Mission 1 through Mission 8
5. ending material
6. `review` candidates and developer/unreachable text

Mission 0 should become the first vertical slice because it exercises the
renderer, controls, UI, resource loading, and a full mission transition before
the whole script is committed to a target format.

### Style decisions to record

Maintain a small project glossary alongside the TSV:

- character names and forms of address;
- police/security organization names;
- location spelling;
- item and weapon terminology;
- punctuation and quote style;
- profanity/intensity policy;
- line-breaking conventions once renderer limits are known; and
- whether repeated system strings must remain byte-identical.

The English should sound natural in context. Literal phrasing is not a useful
substitute for preserving character voice and visible meaning.

## Phase 3: runtime trace before behavior changes

Use an emulator with a Japanese System Card BIOS and debugger support.

### Minimum trace objectives

- Break on BIOS `$E060` (`EX_GETFNT`).
- Find callers associated with dialogue display.
- Trace how the record marker is consumed.
- Log each low-byte control and the renderer state before/after it.
- Determine visible line width, row count, page behavior, and input timing.
- Identify whether controls influence voice/audio playback.
- Record the source payload address for displayed records.

### Coverage log

Create a runtime log keyed by `entry_id` or payload offset:

| Field | Purpose |
|---|---|
| offset/entry ID | connect runtime behavior to inventory |
| mission/scene | translation context |
| speaker | voice consistency |
| screenshot | visual proof and layout |
| controls observed | semantics research |
| visible width/rows | renderer requirements |
| reachable | separate shipped-but-unused data |

Instrumentation should be behavior-neutral until the original path is
understood.

## Phase 4: same-size insertion proof

Implementation status: the `mission0-stock-renderer` build completes the
static and raw-sector portions of this phase for 271 visible runs. They cover
startup text, both copies of all seven opening profiles, mission-title
subtitles, the opening Mission 0 bartender exchange, the complete ten-page
opening narration, and all three Media Mix merchandise pages. The builder
authenticates the source, uses same-size fullwidth Shift-JIS, preserves all
narration and dialogue controls, uses lowercase Mission 0 glyphs, keeps
punctuation inside the code-confirmed 11-cell limit, and reflows only confirmed
row-addressed profile and Media Mix records. It applies no dialogue code
patches. Mode 1 EDC/ECC rebuilding covers 21 changed absolute LBAs with the
original title. The default clean-title variant changes 14 additional sectors:
one palette sector and 13 visible title-tile sectors.

The earlier build has an informal user report that it mostly works. Exact
emulator, BIOS, save/load, audio, and failure details have not yet been recorded
in the project evidence, so they remain the human gate for v0.6. v0.5's
13-cell wrapping specifically failed runtime review and is retained only as
historical evidence. The Media Mix additions in v0.7 require their own
screenshots because they use a different row-addressed text path.
The v0.9 profile screens and antialiased title require the same screenshot
gate; structural validation cannot prove live palette selection or timing.

Before changing any renderer code:

1. Choose short, confirmed-visible lines.
2. Use same-size fullwidth Shift-JIS English or another representation already
   accepted by the original renderer.
3. Modify a disposable payload/image copy.
4. Rebuild the affected raw sector's EDC/ECC.
5. Verify all track boundaries and source-unmodified sectors.
6. Boot and display the lines.
7. Confirm save/load and the next track transition still work.

The automated builder proves the address-to-disc rebuild path independently of
the English font project. The compact-renderer experiment is frozen at commit
`3abaf64` and is not part of the playable build. Human testing must still prove
runtime behavior.

## Phase 4b: packed final-dialogue insertion

The final 2026-09-24 localization workbook is now an authenticated editorial
input rather than an informal external reference.

```bash
python -m pip install -e ".[dev,editorial]"

cyber-oedo export-final-dialogue \
  Cyber_City_Oedo_808_Final_Localization_2026-09-24.xlsx \
  final_dialogue_2026-09-24.tsv

cyber-oedo build-packed-dialogue-test \
  "Cyber City Oedo 808 - Kemono no Alignment (Japan).ccd" \
  packed-dialogue-test \
  final_dialogue_2026-09-24.tsv \
  /path/to/user-supplied-font.ttf
```

The build is fail-closed:

- the workbook and exported TSV hashes are fixed;
- each row must map to an exact `27 28` marker and exact Shift-JIS source span;
- exact-footprint packed English is enabled immediately; shorter rows are
  reported as padding candidates until the ignored-padding behavior is certified;
- packed English that exceeds the owned span is reported for relocation rather
  than shortened;
- rows whose workbook representation is not one contiguous binary span are
  reported for record-aware mapping;
- only Mission 0 is activated today because later overlay font-hook residency
  has not yet been certified.

The test profile emits both a build manifest and a Mission 0 relocation queue.

## Phase 5: stock-renderer page design

A release-quality record should satisfy:

- fullwidth Shift-JIS glyphs accepted by the original path;
- explicit translator-approved 11-cell lines;
- explicit page boundaries using only mapped controls;
- record-specific visible line limits;
- preservation of every non-page control;
- preservation of control timing and audio interactions; and
- deterministic rendering for screenshots and regression tests.

Do not add a parser escape, compact glyph path, or code cave to the playable
profile. Accurate longer English should use more pages in a relocated stock-
renderer record after the resource entry path is mapped.

The stock profile retains the stable word-wrap formatter. It pads fullwidth
spaces until the existing 11-cell cursor wraps naturally. The retired v0.6
punctuation hook is absent; punctuation must fit the ordinary line budget.
`PageBreakPlan` extends that approach by compiling explicit pages without
changing renderer code.

The Media Mix fix does not change that conclusion. Those pages already carry
explicit tile-row operands, so their overlap can be corrected by reassigning
records to rows two tiles apart. Dialogue lacks that same per-line layout
structure.

### Font questions

- Where can font tiles be stored without displacing referenced data?
- Are glyphs uploaded to VRAM per character or cached?
- How many tile indexes are available?
- Are punctuation and lowercase needed?
- Can a proportional-width table fit in RAM?
- Does the background/window renderer assume 16-pixel advances?

## Phase 6: pointer and length mapping

For each named resource containing text:

1. identify the header and true region boundary;
2. locate every pointer/offset/length field;
3. determine whether offsets are absolute, module-relative, or sector-relative;
4. identify alignment and terminator rules;
5. distinguish data padding from runtime scratch/copy space;
6. write a parser that round-trips the unmodified resource byte-for-byte; and
7. add fixed-size and boundary tests before relocation.

`analyze_text_slots.py` helps prioritize regions with large constant-fill tails.
It does not establish ownership of those bytes.

`dialogue_relocation.py` now implements the guarded part of this contract.
`PointerSite` requires exact pointer arithmetic, `RelocationArea` requires
exact destination bytes inside a proven loaded extent, and
`DialogueRelocationPlan` refuses an empty pointer list. No real relocation is
active yet.

The opening `KURUZER` narration begins inline at resource offset `+0x28`.
Static searching has not proven a pointer to that marker. Treat it as an inline
command-stream candidate until a runtime trace establishes a different access
path.

### Reinserter contract

An activated reinserter must:

- accept a validated inventory and explicit encoding;
- reject missing/duplicate IDs;
- reject unrecognized controls;
- enforce per-record or per-region capacity;
- produce a relocation map;
- update every mapped pointer/length;
- leave unrelated payload bytes unchanged;
- report every modified payload sector;
- rebuild Mode 1 EDC/ECC for those sectors;
- preserve the CloneCD track/subchannel geometry; and
- emit a verification report and patch format, not overwrite the source image.

See `renderer_freeze_and_relocation.md` for the frozen experiment, exact
`KURUZER` evidence, page compiler, relocation gates, and stop conditions.

## Phase 7: vertical-slice QA

Complete Mission 0 before scaling translation insertion to later banks.

Test:

- new game and tutorial text;
- every dialogue branch reachable in the mission;
- inventory/item descriptions;
- menus and system notices;
- pauses, page breaks, and fast-forward behavior;
- voice/audio synchronization;
- save and load;
- mission completion;
- transition into the next mission/audio track; and
- emulator restart from the saved state.

Compare against the unmodified disc whenever behavior is ambiguous.

## Phase 8: full-game release gate

Static tests are necessary but not sufficient. Before public release:

- play every mission and ending;
- exercise optional branches and failure paths;
- test save/load at every supported boundary;
- check every item/person/location database page;
- inspect all screenshots for clipping, orphaned punctuation, or stale Japanese;
- test at least two compatible emulators;
- if practical, test original hardware or an accurate optical-drive emulator;
- verify patch application from a clean, hash-matching source; and
- document known limitations and required System Card version.

## Regenerating analysis without losing translations

`build_translation_inventory.py` creates a fresh file and leaves translation
columns blank. Do not overwrite the translator's master TSV when a scanner
changes.

Instead:

1. generate to a new filename;
2. validate both old and new inventories;
3. join translations by stable evidence, preferably original `offset` plus
   `source_text`;
4. use `canonical_id` only as a secondary consistency aid because canonical
   numbering can shift when earlier discoveries change;
5. review added, removed, or changed rows manually; and
6. validate the merged result.

A future migration utility should use source hash, offset, raw bytes, and source
text together rather than assuming IDs are permanent across extraction changes.

## Definition of done by milestone

### Static-analysis milestone

- reproducible payload hash;
- documented address model;
- generated dialogue/auxiliary inventory;
- heuristic limits identified;
- synthetic tests pass.

### Insertion-proof milestone

- immediately visible startup text patched;
- raw-sector integrity rebuilt;
- unmodified sectors verified;
- emulator boot/display confirmed;
- new game reaches controllable Mission 0; and
- save/load and CD audio paths pass their first smoke test.

### Renderer milestone

- Latin encoding documented;
- wrapping/control behavior tested;
- Mission 0 fully translated and playable.

### Release milestone

- full translation inserted;
- full-game manual test complete;
- clean-source patch verified;
- release documentation and hashes published.
