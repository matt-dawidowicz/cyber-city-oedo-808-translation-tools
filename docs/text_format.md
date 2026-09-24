# Text format and inventory schemas

## Confirmed dialogue record shape

The main dialogue scanner looks for:

```text
27 28  [Shift-JIS glyphs and one-byte controls]  00
```

- `27 28` is the observed record marker.
- `00` terminates the record.
- Two-byte Shift-JIS lead bytes are `81-9F` and `E0-EF`.
- Two-byte trail bytes are `40-7E` and `80-FC`.
- Halfwidth Katakana uses single bytes `A1-DF`.
- A byte below `80` inside the body is preserved as an opaque control.

The payload offset and `record_bytes` include the marker and terminator.
`tagged_text` excludes the marker/terminator but includes controls in the form
`<$XX>`. `text` contains only decoded glyphs.

Conceptual example:

```text
raw:          27 28 [SJIS text] 40 [SJIS text] 00
tagged_text:  Japanese text<$40>Japanese text
text:         Japanese textJapanese text
controls:     40
```

Do not read `21`, `2F`, `40`, or `5C` as ASCII `!`, `/`, `@`, or `\`. Their
frequency and placement show that they are bytecode/layout controls in this
record format.

## Control dispatch confirmed from code

| Byte | Observed count in the initial dialogue corpus | Proven behavior |
|---|---:|---|
| `40` | 1,538 | explicit line advance; scroll when advancing into row 3 |
| `2F` | 1,004 | wait up to 20 vertical blanks unless held input shortens it |
| `21` | 831 | wait for active ADPCM voice playback to finish unless trigger input skips it |
| `5C` | 18 | wait for an input press and subsequent full release |
| `2A` | not part of the original extraction allowlist | consume one digit-like operand and set glyph delay `$2827 = operand-$30` |
| `7E` | not part of the original extraction allowlist | consume one digit-like operand and set cell attribute `$2763 = operand-$30` |
| `3D` | structured dynamic insertion | select one 32-byte `$A400` record and render its active text field |

`COMMON_DIALOGUE_CONTROLS` in `game_layout.py` is an extraction allowlist,
not the complete interpreter opcode set. The runtime dispatcher is now compared
across both Mission 0 copies and Missions 1-8 and is relocation-equivalent in
all ten overlays.

For `21`, `$37F1` is no longer an unknown flag. The reusable ADPCM driver
writes the active voice/sample selector there when playback starts, polls System
Card `AD_STAT`, and clears `$37F1` when playback becomes idle. The parser
therefore uses `21` as an interruptible voice-synchronization barrier.

Before assigning a more specific user-facing name:

1. break on or trace the dialogue renderer;
2. display records containing the value in several contexts;
3. correlate the byte with cursor position, line/page transitions, delay, input,
   and audio state;
4. test repeated forms such as `2F 2F`; and
5. record counterexamples before changing the tag syntax.

## Why normal ASCII insertion is unsafe

The existing parser consumes low ASCII-range values as control bytes. Writing
`HELLO` into a record would therefore produce five unknown commands, not five
Latin glyphs.

The boot program calls the System Card BIOS `EX_GETFNT` routine at `$E060` and
uses 16x16 glyph transfer mode for Shift-JIS. The playable profile uses
fullwidth Shift-JIS Latin through that original path. The experimental compact
escape/font path is frozen at commit `3abaf64` and is not imported by the
builder.

Fullwidth lowercase Latin is available in the same Shift-JIS path and already
appears in shipped resources such as `Ｄｒｉｖｅ　Ｒｅａｄｙ．`. The v0.6
test profile therefore uses lowercase without replacing the glyph path.

Static disassembly now confirms the active Mission 0 glyph routine at CPU
`$5915`. It calls `$5946`, which returns an 11-cell ordinary line limit and a
12-cell limit for punctuation listed at `$5968`. The prior screenshot-derived
13-cell estimate was wrong. This explains the failed v0.5 layout: its padding
crossed the real boundary, producing visible spacing errors and broken words.

The original punctuation table includes Japanese comma/stop (`81 41`,
`81 42`) but not fullwidth English comma/period (`81 43`, `81 44`). The v0.6
test hook extended the default lookup path for those two English codes. The
current stock profile retires that hook and keeps English punctuation inside
the ordinary 11-cell limit.

The v0.6 formatter pads narration lines to 11 cells. This moves the existing
automatic cell wrap to a word boundary without inserting `2F`, `40`, or
another control. It does not increase the number of visible cells per line.

Do not choose an escape byte for the playable build. Use mapped page breaks and
pointer-aware relocation without changing the parser or renderer.

## Page-only relocated records

`dialogue_relocation.py` compiles only a narrow, explicit record shape:

```text
27 28 [fullwidth page 1] 40 [fullwidth page 2] ... 00
```

The source record must contain only `40` controls. A translator supplies each
page's explicit lines and a record-specific `PageGeometry`. Non-final lines
are padded to the known cell width so the stock renderer wraps between words.

The compiler does not remove source page breaks. Added pages require explicit
opt-in and runtime testing. Records containing `21`, `2F`, `5C`, or other
controls are rejected until a record-specific control template can preserve
their exact sequence and semantics.

Compilation does not authorize relocation. `PointerSite`, `RelocationArea`,
and `DialogueRelocationPlan` require proven reachability, exact destination
ownership, loaded-resource containment, and full 16-bit pointer arithmetic.

## Media Mix information-screen records

The three promotional information pages use a simpler format than dialogue:

```text
00 01 RR  [fullwidth Shift-JIS text]  00
```

- `00 01` introduces a row-addressed line;
- `RR` is the destination background-map tile row;
- the Shift-JIS string is null-terminated; and
- separate color commands may appear between records.

The source body assigns rows `08`, `09`, `0A`, and so on, while the active BIOS
font path produces 16-pixel-tall glyphs. Because a tile row is 8 pixels,
consecutive source rows overlap by half a glyph. This is an original
data-layout property, not screenshot blur and not a flattened graphic.

The profile treats each command and text run as one
`InformationScreenLine`. Visible English is placed on rows at least two apart.
Superseded records remain the same byte size, contain only fullwidth spaces,
and are assigned to offscreen row `1E`. The original opcode, null terminator,
record order, page boundaries, and all non-row control bytes remain unchanged.

Record order is also animation order. Visible `display_row` values must rise by
at least two in tuple/source order, not merely form a valid set after sorting.
When one late decorative record was moved above earlier records, the final
layout was readable but its lines appeared out of order. The English layout
therefore keeps each visible item in one original record, shortens wording
where necessary, and gives every body line the same three-cell left margin.
This keeps alignment, reveal order, and visual order consistent without
changing record capacity.

This method is specific to the Media Mix page interpreter. It does not increase
the dialogue renderer's 11-cell width and must not be generalized to dialogue
without runtime evidence.

## Opening profile records

Opening dossiers use a parallel row-addressed structure:

```text
00 0C RR  [fullwidth Shift-JIS text]  00
```

The text is still null-terminated and `RR` is still an 8-pixel background-map
row, but opcode `00 0C` identifies the dossier interpreter rather than the
Media Mix page interpreter. Record numbers, separators, portrait selection, and
other screen controls occur outside the translated string ranges.

Seven profiles appear twice at different payload offsets. Each
`OpeningProfileField` therefore stores both offsets and requires both guarded
copies to be patched. Most source strings are identical. Gogul's alias is the
documented exception: the primary bank contains a longer alias while the
repeated bank contains only `ゴーグル`. The model accepts that difference
explicitly and never searches approximately.

The Japanese name and romanized name occupy rows `04` and `05`, which overlap
because the glyph is 16 pixels tall. The English layout clears the Japanese
line on offscreen row `1E` and moves the romanized line to row `04`. Profiles
with a charge continuation use visible rows `14`, `16`, `18`, and `1A` for the
charge, continuation, alias, and bounty. Profiles without a continuation keep
the original even rows.

Every replacement remains fullwidth Shift-JIS and exactly matches its source
byte length. Short English is padded with fullwidth spaces; record opcodes,
null terminators, order, portrait data, and unmodified fields remain unchanged.


## Ending mixed text records

The ENDING bank does not contain the common Mission 0-8 dialogue overlay. Its
mission-complete/save/credit presentation uses a separate command stream:

```text
00 PP RR [null-terminated Shift-JIS]
01 PP RR [null-terminated Shift-JIS]
02 PP RR [null-terminated ASCII]
FF
```

The two bytes labeled `PP RR` are position/control operands consumed by the
ending-specific handlers.

- opcode `00`: Shift-JIS through the generic ending text path;
- opcode `01`: Shift-JIS through an ending-specific `EX_GETFNT` path;
- opcode `02`: fixed-width ASCII, used by the credits;
- `FF`: stream terminator.

The credits are therefore text-backed ASCII records, not a flattened graphic.

The separate ENDING OEDONET/news stream also contains row-addressed Shift-JIS
records, but mixes them with additional formatting/page commands. Its complete
source extent is guarded while the remaining non-text opcodes stay explicitly
partially decoded.

## Fixed command/system UI table

The common Mission 0-B and Mission 1-8 text overlays contain a fixed table of
37 16-byte entries beginning at relative `$C000`. Each entry begins with a
null-terminated Shift-JIS label followed by per-entry metadata.

This table contains visible commands and system functions such as Look, Talk,
Examine, Inventory, System, Move, mode selection, forensic tools, and Varsus
functions. These labels are therefore text-backed even when their on-screen
presentation resembles pre-rendered UI graphics.

The earlier Mission 0-A overlay has a distinct variant and is treated
separately.

## Dynamic name/place/item records

The 769-byte source block later installed at `$A400` contains 24 32-byte
records, each with a primary text slot, an alternate text slot, and state bytes.
The strings include people, generic descriptors, places, and item/object labels,
so this is a general dynamic-label system rather than only a character-name
table.

## Extraction-confidence labels

### `likely_text`

The candidate has enough Japanese characters, no halfwidth Katakana, and only
the common observed control values. It is likely a valid text record.

### `review`

The candidate is retained but contains a shape associated with more false
positives, such as halfwidth Katakana or an uncommon control.

These labels do not answer:

- whether the record is reachable;
- whether a player sees it;
- whether it is duplicate/developer text;
- whether the translation context is known; or
- whether it can be safely expanded or relocated.

## `dialogue.tsv`

| Column | Meaning |
|---|---|
| `bank` | mission/ending analysis region from `game_layout.py` |
| `quality` | `likely_text` or `review` extraction confidence |
| `offset` | marker byte offset in the 2048-byte payload |
| `sector` | `offset // 2048` |
| `within_sector` | `offset % 2048` |
| `record_bytes` | marker through null terminator, inclusive |
| `sjis_characters` | decoded glyph count, controls excluded |
| `controls` | control byte values in encounter order |
| `tagged_text` | decoded glyphs with controls rendered as `<$XX>` |
| `text` | visible decoded glyphs only |
| `raw_hex` | exact marker/body/terminator bytes |

The `raw_hex` field is the strongest audit trail: a developer can verify that
an extraction row still matches the source payload.

## `likely_shift_jis.tsv`

This broad scanner output contains:

| Column | Meaning |
|---|---|
| `offset`, `sector`, `within_sector` | payload address |
| `bytes` | matched byte length |
| `characters` | decoded Unicode character count |
| `hiragana`, `katakana`, `kanji`, `fullwidth` | heuristic metrics |
| `text` | decoded candidate |

It is useful for discovering labels and database text that do not use the
dialogue marker. It is not proof of a self-contained string.

## `auxiliary_text.tsv`

This contains broad Shift-JIS candidates whose byte intervals do not overlap
any dialogue record:

| Column | Meaning |
|---|---|
| `bank` | analysis region |
| `offset`, `sector`, `within_sector` | payload address |
| `bytes` | matched bytes |
| `characters` | decoded characters |
| `text` | candidate text |

Auxiliary strings can live inside fixed tables. Their termination, pointers,
and capacity must be examined per structure before editing.

## `translation_inventory.tsv`

This is the translator-facing file:

| Column | Editable? | Meaning |
|---|---|---|
| `entry_id` | no | unique occurrence ID in offset order |
| `canonical_id` | no | groups identical visible source text |
| `occurrence_count` | no | number of rows with that visible source text |
| `kind` | no | `dialogue` or `auxiliary` |
| `bank` | no | mission/ending analysis region |
| `quality` | no | extraction-confidence label |
| `offset` | no | payload byte address |
| `sector` | no | payload sector |
| `source_bytes` | no | source record or matched run length |
| `controls` | no | dialogue controls in encounter order |
| `source_text` | no | visible source glyphs |
| `tagged_source` | no | source with `<$XX>` controls |
| `english_translation` | **yes** | natural visible English |
| `translator_notes` | **yes** | context, uncertainty, screenshot, QA notes |

Canonical IDs group `source_text`, not complete records. The same canonical ID
can therefore occur with different control layouts. Reuse wording only after
checking each occurrence.

## Duplicate and context policy

The inventory is occurrence-level because a translation patch ultimately needs
addresses. A translator may filter by `canonical_id` to work on unique text,
then propagate a preferred translation to matching occurrences.

If context requires different English for the same canonical source, different
translations are permitted. `validate_translation_inventory.py` reports that as
a warning so it is reviewed intentionally.

## Spreadsheet handling

- Preserve tabs; do not export as comma-separated text.
- Preserve UTF-8. Generated translator-facing TSVs include a BOM for common
  spreadsheet compatibility.
- Do not allow a spreadsheet to reinterpret `offset` or IDs as numbers/dates.
- Avoid sorting only part of the table.
- After saving, run `validate_translation_inventory.py`.
- Keep a versioned copy before bulk fill or find/replace.

## Fixed-size editing is not yet authorized

`source_bytes` is evidence about the original occurrence, not an English byte
budget. There is no current ASCII encoder, line wrapper, pointer updater, or raw
sector rebuilder. Translation can proceed in Unicode independently of those
constraints while engine work determines the real target representation.
