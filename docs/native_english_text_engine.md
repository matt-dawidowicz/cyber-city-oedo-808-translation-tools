# Native English dialogue engine

Status: compiler implemented; runtime rewrite in progress.

## Decision

The final English translation will not be constrained to the Japanese 16x16
cell renderer and will not use the packed two-character private-Shift-JIS
format as its release architecture.

The packed renderer remains useful as a compatibility/proof experiment, but
the release target is a dedicated English mode inside the common Mission 0-8
dialogue engine.

## Record format

The outer dialogue marker remains unchanged:

```text
27 28
```

A translated record then begins with the dedicated English-mode signature:

```text
7D 45
```

After that signature:

- `80-FE` = one English display glyph each;
- `00` = stream terminator;
- `21` = voice synchronization barrier;
- `2A xx` = glyph-delay command;
- `2F` = interruptible timed wait;
- `3D xx xx` = indexed/dynamic text command;
- `40` = line advance;
- `5C` = wait for press then release;
- `7E xx` = per-cell/display attribute command.

The signature is recognized only immediately after a proven `27 28` record
marker. It is not a global escape sequence.

Stock Japanese records continue through the original interpreter unchanged.

## Encoding

English uses one byte per visible character.

The reviewed final localization currently requires fewer than 127 display
characters, so the `80-FE` namespace is sufficient without a pair dictionary.
The build creates a deterministic glyph table from the reviewed English
corpus and a user-supplied font source.

This removes:

- fake Shift-JIS private glyph tokens;
- two-character pair dictionaries;
- odd-character padding;
- the need for a 16x16 cell to represent two unrelated Latin glyphs.

## Geometry

The existing dialogue field is approximately 11 ordinary 16-pixel cells wide,
or 176 horizontal pixels.

The native English target is therefore:

- 8-pixel glyph width;
- 16-pixel glyph height;
- **22 ordinary English characters per line**;
- three visible 16-pixel text rows;
- explicit `40` line advances;
- existing scroll behavior when advancing beyond the third row.

The release renderer should operate in 8-pixel BAT columns rather than making
the stock cursor believe that every two English letters are one Japanese cell.

## Control preservation

The source corpus audit covers all 2,237 final spoken/narration rows:

| Class | Records | Policy |
|---|---:|---|
| no semantic mid-text control | 2,005 | automatic compile |
| only mid-text `40` line advances | 153 | discard Japanese wrapping and recompute English wrapping |
| semantic control between visible runs | 79 | explicit control anchor required |

Thus **2,158 / 2,237 records (96.5%)** can be compiled automatically without
guessing timing placement.

The 79 manual-anchor records contain controls such as timed waits or indirect
text between visible source runs. They remain a small, explicit editorial QA
queue rather than being proportionally or heuristically repositioned.

## Storage consequences

One-byte English is compact, but proper English is still longer than Japanese
in many records.

Using the new signature, 22-column word wrapping, preserved boundary controls,
and no semantic-anchor guessing:

- 488 final records fit their current complete record footprint;
- 1,670 require record/resource growth;
- 79 require explicit semantic anchors before final size classification.

Mission 0 alone currently classifies as:

- 87 current-footprint candidates;
- 328 growth-required;
- 18 manual-anchor records.

This confirms that **rewriting the renderer does not eliminate the need for
relocation/resource expansion**. It eliminates the artificial Japanese
typography constraint so relocation can preserve the actual approved English.

## Runtime rewrite boundary

The stock shared renderer interval `$5444-$5B19` is byte-identical across ten
Mission 0-8 overlay instances. The rewrite should replace the common text
presentation layer once and then apply relocation-adjusted hooks in each
overlay.

The current stock state that must be replaced or adapted is:

```text
cursor column  $30
cursor row     $2F
grid           $26F3
grid geometry  3 x 12 cells
cell bytes     SJIS-high, SJIS-low, attribute
BAT base       $7900
glyph VRAM     $6D00
```

The native English grid should store one glyph ID plus attribute/state per
8-pixel column, or bypass the old 3-byte grid entirely if live redraw/scroll
tests show that a direct BAT/VRAM representation is simpler.

## Implementation phases

### Phase A — compiler

Implemented in `cyber_oedo/text/english_dialogue_engine.py`:

- deterministic one-byte glyph table;
- 22-column English wrapping;
- `7D 45` English record signature;
- preservation of leading/trailing semantic controls;
- automatic replacement of Japanese `40` wrapping;
- rejection of semantic mid-text controls without explicit anchors.

### Phase B — Mission 0 parser dispatch

At the common dialogue entry:

1. inspect the first two body bytes;
2. if they are `7D 45`, advance past the signature and enter the English
   interpreter;
3. otherwise execute the original parser byte-for-byte.

This makes the rewrite opt-in per record and preserves stock fallback.

### Phase C — native 8x16 glyph renderer

Replace the English-mode glyph path with:

1. decode one byte to glyph ID;
2. fetch 16 row bytes from the English atlas;
3. upload one 8x16 glyph as two 8x8 PCE tiles;
4. write the two vertical BAT entries for the current 8-pixel column;
5. advance the English column by one;
6. retain existing delay/input/voice semantics.

The Japanese path remains unchanged.

### Phase D — English grid/scroll rewrite

The old 3 x 12 x 3-byte Shift-JIS grid cannot remain the authoritative redraw
model for 22-column English.

Implement a 3 x 22 English grid (glyph ID + attribute) or prove a smaller
direct-render state sufficient for:

- redraw;
- line advance;
- row-3 scroll;
- punctuation/timing;
- save-state stability;
- dialogue return and selective VRAM restore.

### Phase E — storage relocation

Move final records into owned expanded resources instead of shortening prose.
The compiler output, not the Japanese record length, determines required
capacity.

### Phase F — all overlay instances

Once Mission 0 is live-certified, apply the same engine rewrite to the nine
other renderer-bearing overlays using their proven relocation-equivalent
parser/renderer copies.

## Release gates

The native engine is not release-enabled until:

1. the English signature is proven collision-free at every source record;
2. Japanese fallback still renders identically;
3. all seven known dialogue controls match stock timing/behavior;
4. 22-column wrapping and three-row scrolling are visually verified;
5. mid-control anchor records are reviewed explicitly;
6. relocated records survive save/load and scene transitions;
7. Mission 0 is completed end-to-end;
8. representative later missions prove overlay portability.

## Superseded assumption

The prior packed-English pair renderer should no longer be treated as the
release text architecture. It remains a useful experiment demonstrating that
a custom atlas can coexist with the stock VDC path, but the final project goal
is native one-byte English and a rewritten English cursor/grid renderer.
