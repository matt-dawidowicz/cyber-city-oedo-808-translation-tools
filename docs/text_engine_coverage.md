# Game-wide text-engine coverage

This document classifies the game's text and text-like presentation systems by
storage format, runtime consumer, and evidence strength. It complements
`gamewide_runtime_architecture.md`, which proves the common exploration and
dialogue machinery.

## Coverage result

The game does **not** have one universal text file or one universal text
interpreter.

The major split is:

1. Missions 0-8 share one relocation-equivalent dialogue bytecode parser and
   one byte-identical stock renderer/window implementation.
2. Startup/opening screens use several fixed and row-addressed Shift-JIS
   formats outside that dialogue bytecode.
3. Mission overlays also use named binary UI/overlay resources resolved by a
   shared descriptor/cache/loader path; these are not another direct Shift-JIS
   text family.
4. The ENDING bank does not contain the common dialogue overlay. It uses
   separate presentation command streams, including a dedicated ASCII credit
   path.
5. The opening title is genuinely graphics-backed rather than runtime text.

Run:

```bash
cyber-oedo prove-text-engine-coverage track02_mode1_2048.bin \
  --output text_engine_coverage.json
```

For the final information-page, descriptor, and translation-ownership layer, see
[`text_engine_completion.md`](text_engine_completion.md) and run
`cyber-oedo prove-text-engine-completion`.

The command authenticates the payload, validates fixed source regions, validates
the existing startup/Media Mix/dossier source models, compares common UI copies,
decodes the dynamic-label records and ending mixed text stream, inventories
named resource families, and reports the graphics-backed title source hash.

## Common dialogue overlays

There are ten common renderer-bearing overlays, but they are not one-per-bank:

| Instance | Analysis bank |
|---|---|
| MISSION_0_A | Mission 0 |
| MISSION_0_B | Mission 0 |
| MISSION_1 | Mission 1 |
| MISSION_2 | Mission 2 |
| MISSION_3 | Mission 3 |
| MISSION_4 | Mission 4 |
| MISSION_5 | Mission 5 |
| MISSION_6 | Mission 6 |
| MISSION_7 | Mission 7 |
| MISSION_8 | Mission 8 |

The ENDING bank has no copy of the common renderer signature or parser anchor.

The complete renderer/window interval from logical $5444 through $5B19 is
1,750 bytes and is byte-identical across all ten copies. This covers the shared
VRAM bases, font acquisition/transform, VDC streaming, cell drawing, cursor and
wrap logic, text-grid update, pacing, redraw, scroll, and initialization.

The parsers themselves are relocated rather than byte-identical because their
absolute call/jump targets move with each overlay. After accounting for the
relocation delta, their non-address bytes, targets, and opcode comparisons are
equivalent.

## Dialogue controls

The shared parser language is now:

| Value | Proven behavior |
|---:|---|
| 00 | terminate the current stream |
| 40 | explicit line advance; scroll when entering row 3 |
| 2A | consume a digit-like operand and set glyph delay $2827 to operand-$30 |
| 2F | up to 20 vsyncs of delay, shortened by held low joypad bits |
| 5C | wait for a controller press and then full release |
| 7E | consume a digit-like operand and set the per-cell attribute to operand-$30 |
| 3D | render the active field from one indexed 32-byte dynamic-label record |
| 21 | wait for the active ADPCM voice to finish, unless trigger input skips it |
| >80 | ordinary two-byte Shift-JIS glyph pair |
| <=80 other | ignored by this dispatcher |

### Control 21 and $37F1

$37F1 is no longer an unknown asynchronous flag.

The reusable ADPCM driver latches the selected voice/sample identifier into
$37F1 when playback starts. Its completion loop calls System Card AD_STAT and
clears $37F1 when ADPCM becomes idle.

The parser's 21 control:

1. continues immediately when $37F1 is zero;
2. otherwise remains in the wait path while voice playback is active; and
3. allows controller trigger bits $222D & 3 to break the wait.

Thus 21 is an interruptible **voice synchronization barrier**.

## Cursor, window, and renderer state

The common dialogue renderer has:

- cursor column: $30;
- cursor row: $2F;
- text-grid base: $26F3;
- geometry: 3 rows x 12 cells;
- cell size: 3 bytes;
- cell fields: Shift-JIS high byte, low byte, attribute;
- ordinary width: 11 cells;
- selected punctuation may use cell 12;
- BAT base: $7900;
- glyph-pattern VRAM base: $6D00.

Line advance resets the column and advances the row. Advancing into row 3
scrolls rows 1-2 over rows 0-1 and blanks the final row.

The complete renderer path is therefore:

```text
stream / dynamic string
      |
      v
cursor-aware cell dispatcher
      |
      v
EX_GETFNT -> $4C6C
      |
      v
font transform -> $4C8C
      |
      v
VDC glyph-pattern upload
      |
      v
BAT cell write
      |
      v
cursor/grid/pacing update
```

## Non-dialogue text-family matrix

| Family | Storage | Main scope | Runtime/rendering family | Status |
|---|---|---|---|---|
| Common dialogue | 27 28 bytecode ... 00 | M0-M8 | shared relocated parser + common renderer | source-guarded |
| Dynamic names/places/items | 24 x 32-byte records | common text overlays | opcode 3D -> common renderer | source-guarded |
| Command/system UI | 37 x 16-byte entries | M0-B, M1-M8 | overlay UI | source-guarded/cross-copy matched |
| Startup/save/memory UI | fixed Shift-JIS | boot/startup | startup UI | source-guarded |
| Mission titles | fixed Shift-JIS | M1-M8 and duplicates | title presentation | source-guarded |
| Opening dossiers | 00 0C row + Shift-JIS | opening | row-addressed dossier interpreter | source-guarded |
| Media Mix | 00 01 row + Shift-JIS | startup extras | information-screen interpreter | source-guarded |
| Named binary UI assets | 16-byte name -> sector/span/length descriptors | mission overlays | common lookup/cache/install path | source-guarded; no direct Shift-JIS |
| Information pages / OEDONET | opcodes 00-0A with positioned Shift-JIS and BAT commands | startup, missions, ending | shared information-page interpreter family | command language decoded/source-guarded |
| ENDING completion/save | opcode 0/1 + position + Shift-JIS | ending | ending mixed interpreter | decoded/source-guarded |
| ENDING credits | opcode 2 + position + ASCII | ending | dedicated ASCII credit path | decoded/source-guarded |
| Opening title | 960 planar tiles | startup | graphics | source-hash guarded |

## Dynamic names, places, and items

The authenticated 769-byte source block contains:

- 24 fixed 32-byte records;
- a primary null-terminated text slot at +0;
- an alternate null-terminated text slot at +13;
- six state/metadata bytes at +26..+31;
- one trailing byte after the 24 records.

This is the disc source later installed at $A400. The contents include character
identities, generic descriptors, places, and item/object labels, so the table is
not merely a "name table."

## Command/system UI table

The common table beginning at relative $C000 contains 37 fixed 16-byte entries.
Each starts with a null-terminated Shift-JIS label followed by entry metadata.

The table includes ordinary commands and system/investigation functions such as
Look, Talk, Examine, Inventory, System, Move, mode selection, forensic
functions, Varsus functions, and arrest/investigation tools.

The M0-B and M1-M8 copies are byte-identical. The earlier M0-A overlay contains
a distinct startup-era variant and is not silently treated as the same table.

This finding also corrects a prior classification error: many labels that look
"graphic" in screenshots are genuine text-table entries.

## Named binary UI/overlay assets

Names such as `INVENTRY`, `DEN_EREV`, `INTER`, `KANSHIKI`, `KIDOU`,
`SHIRYO`, and `H_JYOUHO` are runtime resource identifiers, not evidence that
the corresponding blobs are text tables.

The completion proof decodes their fixed 16-byte descriptors as:

```text
char name[10]
u16  Track 2 sector
u8   sector span
u24  exact byte length
```

The common overlay resolves these names through a descriptor lookup, resident
resource cache, byte loader, and generic TII install/copy path. Mission 0 live
capture data agrees with the descriptor fields; for example, `INVENTRY` maps to
sector $10ED and exact length $0890 in both static and runtime evidence.

A conservative audit across all targeted descriptor-backed instances finds no
credible direct null-terminated Shift-JIS. These resources are therefore
classified as **binary UI/overlay assets**, not as another hidden text family.
Their individual binary schemas remain unassigned until a consumer proves them.

## ENDING architecture

ENDING deliberately sits outside the common Mission 0-8 dialogue architecture.

### OEDONET/news stream

The ENDING OEDONET stream at payload $0500A800 is one instance of the shared
information-page language also used by startup Media Mix and multiple mission
banks. The common Mission 2-8/ENDING dispatcher and handler window is
byte-identical.

The 0-10 command language is now decoded at the machine-behavior level:
positioned Shift-JIS, glyph VRAM-page selection, glyph delay, termination,
display-phase/update controls, positioned transient state, rectangular BAT/tile
draws, ADPCM/display-marker synchronization, input wait, and display reset.

In particular, opcode 00 is **X + Y + null-terminated Shift-JIS**, not a
style/row record, and opcode 07 is a five-operand rectangular tile-block draw.
The OEDONET tail `08 09 03` is synchronization/marker cleanup, input wait, then
termination.

### Mission-complete/save/credit stream

A second ENDING stream is parsed by the dedicated interpreter around logical
$5C93.

The observed stream uses:

- opcode 0: two position/control bytes + null-terminated Shift-JIS;
- opcode 1: two position/control bytes + null-terminated Shift-JIS, rendered
  through an ending-specific EX_GETFNT path;
- opcode 2: two position/control bytes + null-terminated ASCII;
- FF: stream terminator.

Opcode 2 is the credits path. The source contains fixed-width ASCII credit lines,
including the MADHOUSE/MUTSUKI and NCS copyright lines. Credits are therefore
text-backed, not pre-rendered graphics.

## Graphics-backed text

The opening title remains a genuine graphics-backed exception:

- 256 x 240 pixels;
- 32 x 30 tiles;
- 960 consecutive 8x8 4bpp tiles;
- 30,720 bytes;
- separately guarded palette animation.

Do not classify another label as graphics-backed merely because it appears as
tiles on screen. The command/system UI findings demonstrate why storage and
runtime provenance must be checked first.

## What remains

Static text-engine discovery is now largely complete. Remaining work is
certification and translation engineering:

- collect representative later-mission and ENDING live MPR traces with the
  read-only generic Mesen capture script;
- decode an individual named binary UI asset only when translation requires
  modifying that asset;
- implement relocation only for text families whose pointer ownership,
  destination storage, and lifetime are explicitly proven.

These are certification/implementation tasks rather than discovery of another
unknown universal text engine.
