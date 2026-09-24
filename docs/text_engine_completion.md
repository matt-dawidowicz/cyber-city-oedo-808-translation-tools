# Text-engine completion

This document closes the remaining static architecture gaps after
`text_engine_coverage.md`.

## Shared information-page language

The Media Mix screens, later mission information pages, and the ENDING OEDONET
page use one related information-page command language rather than separate
ad-hoc formats.

Eight copies of the complete dispatcher/handler window are byte-identical in
Missions 2-8 and ENDING. Three earlier copies use the same indirect-dispatch
shape but differ in surrounding implementation details.

The common dispatcher has opcodes 0 through 10:

| Opcode | Operands | Proven machine behavior |
|---:|---|---|
| 00 | X, Y, SJIS...00 | render null-terminated Shift-JIS at explicit coordinates |
| 01 | value | set glyph-pattern VRAM high-page/base selector |
| 02 | delay | set per-glyph delay $BF09 |
| 03 | none | terminate the information-page stream |
| 04 | none | toggle internal display phase $BF05 between $00 and $FF |
| 05 | interval | set periodic display-update interval and arm countdown |
| 06 | X, Y, value | set X/Y state and transiently load a third delay operand |
| 07 | mode, X, Y, W, H | draw a sequential rectangular BAT/tile block |
| 08 | none | wait for ADPCM idle and clear the display-marker sprite state |
| 09 | none | wait through vertical sync until held controller state is nonzero |
| 0A | none | run the information-screen display-reset path |

This corrects an older description of opcode 00 as a "style + row" record. The
first two operands are spatial coordinates.

The rectangular opcode 07 is especially useful for translation work. Its
handler computes a BAT address from X/Y, uses W/H as the rectangle dimensions,
selects a sequential tile block from the mode operand, and writes the rectangle
through the shared VDC block routine.

The ENDING OEDONET stream ends with:

```text
08 09 03
```

which is now understood structurally as display/audio synchronization and marker
cleanup, input wait, then stream termination.

Run:

```bash
cyber-oedo prove-text-engine-completion track02_mode1_2048.bin \
  --output text_engine_completion.json
```

## Named binary UI assets

The names `INVENTRY`, `KANSHIKI`, `KIDOU`, `SHIRYO`, `DEN_EREV`,
`H_JYOUHO`, `INTER`, and related identifiers are runtime resource names.

They are resolved through fixed 16-byte descriptor tables:

```text
+00  char name[10]   NUL-padded ASCII
+0A  u16 sector      little-endian Track 2 sector
+0C  u8  span        number of sectors touched
+0D  u24 byte_length exact byte count
```

The common overlay lookup at $6E36 walks this table in 16-byte steps and uses
$43FA for the name comparison. On a match it installs the sector/span/length
fields used by the resource loader.

The Mission 0 live evidence matches the static descriptor exactly. For example,
the `INVENTRY` descriptor names sector $10ED with a two-sector span and exact
length $0890; the historical byte-loader capture records the same sector and
exact byte length.

The higher-level path is:

```text
resource name
    |
    v
16-byte descriptor lookup
    |
    v
16-slot resident-resource cache
    |
    +-- already resident --> return installed pointer
    |
    v
allocate destination
    |
    v
byte loader: full sectors + remainder
    |
    v
generic self-modified TII memory copy/install
    |
    v
cache installed runtime pointer
```

The post-load helper at $420C is a generic self-modified TII copy primitive. It
is **not** evidence of compression or decompression.

A conservative audit of the named UI asset blobs finds no credible direct
null-terminated Shift-JIS. They are therefore classified as binary UI/overlay
assets, not as another hidden text-table family.

This corrects the earlier broad label "resource-local UI text." Visible text
from these screens must be attributed to the already-proven text tables or to a
separately decoded asset format rather than guessed from the resource name.

## Graphics-backed audit

The opening title remains the only text-like asset currently proven to be
literal graphics:

- 256 x 240 pixels;
- 960 consecutive 8x8 4bpp tiles;
- 30,720 bytes;
- source-hash guarded.

The descriptor-backed UI resources fail both direct-Shift-JIS and naive raw
4bpp-text tests. That is not enough to call them compressed graphics. Their
binary schema remains intentionally unassigned until a consumer proves it.

The practical rule is therefore:

> Do not call a visible label "graphics-backed" merely because it appears in a
> tiled UI. Require storage provenance.

## Translation ownership and relocation

The completion report emits an explicit ownership policy for every major text
family.

### Common dialogue

Occurrence-specific dialogue text is safe to edit under source guards. Growth
beyond the owned occurrence remains relocation-gated until destination storage
and pointer lifetime are proven.

### Dynamic labels

The $A400 runtime table contains 24 fixed 32-byte records. Each text slot is
13 bytes including its terminator. Fixed-field replacement is structurally
understood; expansion requires a redesigned table/renderer contract.

### Command/system UI

The shared command table uses fixed 16-byte records whose trailing bytes contain
metadata. Translation must preserve the record stride and metadata unless that
consumer is deliberately rewritten.

### Information pages

The command grammar is now understood, including positioned text and graphical
rectangle operations. Rewriting a stream can move later commands, so arbitrary
growth remains gated on the caller/source-pointer ownership of each stream.

### Ending completion/save/credits

The dedicated ENDING mixed stream is structurally understood. Same-size edits
are straightforward; growth remains gated on the owning stream boundary and
pointer contract.

### Named binary UI assets

Do not translate these as text. Preserve exact descriptor lengths until their
individual binary formats are decoded.

### Opening title

Use the graphics replacement pipeline. It is not a text-relocation problem.

## Live certification

The existing Mission 0 Mesen capture already proves real execution of the
Mission 0 parser/font path, CD byte-loader activity, and MPR changes.

For later missions and ENDING, use:

```text
tools/mesen_text_engine_live_capture.lua
```

The script is read-only and records:

- all known Mission 0-8 dialogue parser entries;
- the common dialogue renderer and font fetch;
- all known information-page dispatcher variants;
- the ENDING mixed parser and renderers;
- CD_READ;
- all eight MPRs;
- cursor state, ADPCM voice state, current/trigger input, and stream pointer
  bytes when meaningful.

Because logical addresses are heavily reused, MPR output is mandatory evidence.
A hit at the expected PC without the expected physical mapping is not a
certification.

## Remaining work after this pass

The remaining text work is no longer discovery of another text engine. It is:

1. collect representative later-mission and ENDING Mesen traces with the generic
   capture script;
2. decode individual binary UI asset formats only when translation requires
   modifying those assets;
3. move from fixed-capacity translation to relocation only where ownership and
   lifetime are explicitly proven.

That is a substantially narrower problem than the original game-wide text
reverse engineering.
