# Translation and patch-development workflow

## Current deliverable boundary

The current deliverable is a reproducible source-text inventory plus documented
analysis tools. It is suitable for:

- script translation;
- terminology and character-voice work;
- runtime coverage planning;
- renderer/control reverse engineering; and
- locating candidate resources and padding.

It is not yet a reinsertion toolchain.

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

Before building a new renderer:

1. Choose one short, confirmed-visible line.
2. Use same-size fullwidth Shift-JIS English or another representation already
   accepted by the original renderer.
3. Modify a disposable payload/image copy.
4. Rebuild the affected raw sector's EDC/ECC.
5. Verify all track boundaries and source-unmodified sectors.
6. Boot and display the line.
7. Confirm save/load and the next track transition still work.

This proves the address-to-disc rebuild path independently of the English font
project.

## Phase 5: English renderer design

A release-quality path should satisfy:

- an escape or state transition that cannot collide with existing controls;
- 8x16 or variable-width Latin glyphs;
- explicit glyph table and fallback behavior;
- English-aware word wrapping;
- predictable line/page overflow behavior;
- preservation of the original Japanese path;
- preservation of control timing and audio interactions; and
- deterministic rendering for screenshots and regression tests.

Prefer a minimal extension around the existing parser. Replacing the complete
text engine increases risk to unrelated Japanese logic and resource loading.

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

### Reinserter contract

A future reinserter should:

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

- one visible line patched;
- raw-sector integrity rebuilt;
- unmodified sectors verified;
- emulator boot/display confirmed.

### Renderer milestone

- Latin encoding documented;
- wrapping/control behavior tested;
- Mission 0 fully translated and playable.

### Release milestone

- full translation inserted;
- full-game manual test complete;
- clean-source patch verified;
- release documentation and hashes published.
