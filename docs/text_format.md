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

## Known controls, unknown meanings

| Byte | Observed count in the initial dialogue corpus | Status |
|---|---:|---|
| `40` | 1,538 | common; exact runtime behavior unconfirmed |
| `2F` | 1,004 | common; exact runtime behavior unconfirmed |
| `21` | 831 | common; exact runtime behavior unconfirmed |
| `5C` | 18 | seen on mission-title records; exact behavior unconfirmed |

`COMMON_DIALOGUE_CONTROLS` in `game_layout.py` is an extraction allowlist. It
does not assign semantics.

To name a control responsibly:

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
uses 16x16 glyph transfer mode for Shift-JIS. Two implementation paths follow:

- A same-size proof can use fullwidth Shift-JIS Latin where it fits.
- A release patch should introduce an unambiguous Latin escape and an 8x16 or
  variable-width font while preserving existing Japanese/control parsing.

Do not choose an escape byte until the runtime parser and all existing controls
are mapped.

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
