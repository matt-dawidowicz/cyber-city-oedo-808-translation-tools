# English text engine v1 design

Status date: 2026-09-10  
Branch: `b3/self-contained-renderer-space-proof-20260910`  
Runtime status: design/build-time contract only; no speculative renderer image

## Decision

The production English path should be designed as a self-contained game-side
text subsystem with embedded font assets. The stock Japanese System Card 3.0
remains an unmodified release dependency. The earlier fontless `EX_GETFNT`
compression route remains a useful fallback and diagnostic reference, but it is
no longer the preferred end-state merely to save font bytes.

Disc storage and runtime memory are separate constraints. Font and translation
assets may be comparatively large on disc; only the code/data that must be live
at the same time needs a proven RAM owner and loader lifetime.

No global escape byte or byte sequence is permitted. Entry into the English
path must be record-, handler-, resource-, or other proven-context-local state
that survives the game's redraw behavior without reinterpreting unrelated data.

## Corpus-derived repertoire

`Cyber_City_Oedo_808_Master_Script.xlsx` was reviewed using the `Canonical
Script` sheet and `working_translation` rows. The authenticated workbook used
for this pass has SHA-256:

`b654d7c3f9861dd1dda546f299d03133f305926b0a5592c3e5628fc06b296999`

There are 2,914 working translated rows and 91 distinct characters in the
current English corpus. All observed characters fit inside this production
contract:

- all 95 printable ASCII characters, U+0020 through U+007E;
- `¥` U+00A5;
- `–` U+2013;
- `—` U+2014;
- `‘` U+2018;
- `’` U+2019;
- `“` U+201C;
- `”` U+201D; and
- `■` U+25A0.

The initial production repertoire is therefore 103 glyphs. This intentionally
contains several printable-ASCII characters not yet used by the corpus so
ordinary English/UI text does not require a font rebuild for trivial additions.

This is a logical glyph repertoire, not an on-disc byte encoding. Byte values
above printable ASCII must not be assigned until the record-local English
selector and control-byte namespace are proven.

## Font roles

The engine should support multiple interchangeable font roles even if the first
runtime proof loads only one.

| Role | Initial purpose | Priority |
|---|---|---|
| `dialogue` | Mixed-case conversation and narration | Required |
| `ui` | Condensed labels, menus, database/news screens | Planned |
| `display` | Headings, terminals, title-like emphasis | Planned |

A scene/module does not need every font resident simultaneously. The eventual
loader may select one font pack per context or retain only the roles required by
that module.

## Initial bitmap format and storage budget

The first target remains an 8x16 stored glyph because it composes naturally into
the game's observed 16x16 cell pipeline: two 8-pixel glyphs can occupy one
existing 16-pixel cell while preserving the stock cell cursor during the first
runtime milestone.

For 103 glyphs at 8x16, one bit per pixel, row-major storage uses one byte per
row:

- one complete font: 103 x 16 = **1,648 bytes**;
- three complete fonts: **4,944 bytes**.

Even a future two-bit-per-pixel representation would be only 3,296 bytes per
font or 9,888 bytes for three complete fonts, before small lookup/metric tables.
Whether the game renderer can profitably use more than one bitplane is not yet
proven and is not part of the first runtime milestone.

Font size therefore is not a reason to compromise lowercase, punctuation, or
visual quality. Runtime residency and rendering cost remain the constraints to
measure.

## Layout model

The build tools now distinguish cell-count layout from pixel layout.

The existing stock renderer path remains available for fullwidth Shift-JIS
proofs. The new typography contract supports:

- explicit glyph coverage validation;
- per-glyph horizontal advance from 1 through 8 pixels;
- exact pixel measurement;
- word wrapping against pixel geometry without splitting words; and
- deterministic packed-font byte budgeting.

A fixed 8-pixel advance is the first runtime target. Once the renderer and
loader are stable, the same contract can accept proportional advances such as a
narrow `I` and wider `M`/`W` without changing translator-facing text.

The first runtime milestone should not require a true half-cell cursor. It can
compose two 8x16 glyphs into one existing 16x16 cell and keep the stock 11-cell
window semantics, yielding up to 22 fixed-width English characters per line.

A later proportional renderer may instead maintain a pixel cursor or render a
whole line/window into scratch graphics memory. That is a separate runtime step
and must be benchmarked against HuC6280/VDC costs.

## Asset and loader architecture

The intended long-term disc organization is logical rather than a commitment
to exact filenames or sectors:

```text
English subsystem
  renderer code
  codec / character map
  dialogue font
  UI font
  display font
  mission- or resource-local English text
```

These assets should be loaded deliberately through a proven game loader path.
They must not be placed in RAM merely because a range appears zero-filled.
Likewise, extending an existing resource past its declared extent is not an
allocation strategy.

The large unused physical capacity of the CD means relocation can favor clean
resource boundaries and maintainability once the disc/loader reference model is
known. Changing track geometry is still a separate concern because audio-track
LBAs and game references must be understood first.

## Relationship to the stock System Card font

The live path `$5915 -> $E060 -> $4C6C -> ~$56C3` remains valuable evidence.
Stock `EX_GETFNT` can still serve three purposes:

1. a reference for the game's expected 32-byte 16x16 glyph-buffer shape;
2. a fallback source for a glyph not present in a loaded custom font; and
3. a diagnostic comparison while reverse-engineering the post-font pipeline.

It should not constrain the production typography if a custom embedded font is
simpler and better-looking once safe RAM and loader ownership are proven.

## Runtime gates that remain

No renderer BIN should be generated from this design alone. Runtime mutation
still requires all of the following:

1. A code/data destination proven owned for the renderer's complete active
   lifetime.
2. A deliberate loader path for renderer/font assets, or equivalent proof that
   an already-owned executable region can contain the required code.
3. A record-/handler-/resource-local one-byte English selector that cannot
   collide with ordinary data and remains correct during redraw.
4. A bounded disassembly of the game routine around `$56C0/$56C3` and its
   downstream `$56xx/$4Exx` bitmap processing.
5. Live read/write tracing of `$4C6C-$4CAB` and representative glyph-buffer
   captures.
6. Continued proof of `$A400` indexed-state lifetime for dynamic fields as
   Mission 0 coverage expands.

`$9F1B-$9FFF` remains forbidden because live System Card access was observed
there. The failed `H_BARTEN` `$0080 -> $0800` extension remains forbidden as a
storage strategy.

## Next implementation milestone

The next useful runtime investigation is not font artwork. It is to map the
Mission 0 loader/RAM-bank lifecycle and bound the post-`EX_GETFNT` renderer.
Once a deliberate resident range is proven, the first playable typography proof
should load exactly one 103-glyph dialogue font and render the live `H_BARTEN`
line through a context-local selector. Only after that survives conversation,
redraw, menu activity, and scene exit should UI/display fonts or proportional
advances be activated.
