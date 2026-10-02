# Definitive VWF runtime contract

The Definitive Edition uses two English rendering modes.

## Fixed compatibility mode

Signature: `7D 45`

This remains the fallback for dynamic/runtime-generated text and for recovery
when a proportional asset is unavailable. Two 8x16 English glyphs occupy one
stock 16-pixel dialogue cell.

## Authored VWF mode

Signature: `7D 56`

Authored dialogue is wrapped by pixel width, then packed into the game's
existing 11-by-3 grid of 16-pixel cells. Each cell contains one or more
proportional English glyphs whose total advance fits within 16 pixels.

The critical invariant is that VWF identity is carried by the cell token itself.
A cell must remain distinguishable as VWF after it has been copied into the
stock redraw/scroll buffer. Redraw may never depend on a transient parser mode
flag.

### Stream

A VWF segment contains:

- `7D 56`
- one or more encoded 16-bit cell tokens
- an explicit segment terminator
- ordinary stock low-byte controls between segments

The stock parser remains authoritative for waits, voice barriers, page
advances, dynamic text, attributes and input waits.

### Cell dictionary

Each mission owns a deduplicated dictionary of VWF cell descriptors. A
descriptor records the ordered glyph IDs needed to reconstruct one 16-pixel
cell. The build-time compiler rejects a cell whose proportional glyph advances
exceed 16 pixels.

The dictionary lives with the mission English pool rather than in overlay code.
This keeps the overlay-resident runtime small and allows the dictionary to grow
with the script.

### Runtime compositor

The font hook distinguishes three cases from the stored cell bytes:

1. stock Japanese cell -> BIOS font path;
2. fixed native-English cell -> existing 8x16 compositor;
3. VWF token -> VWF descriptor lookup and 16x16 composition.

The VWF compositor:

1. decodes the cell token;
2. temporarily maps the Card-RAM bank containing its descriptor;
3. obtains the ordered glyph IDs;
4. composes their normalized 8x16 bitmaps at their proportional X advances into
   the existing 32-byte font staging buffer;
5. restores the prior MPR mapping;
6. returns to the stock transform/BAT path.

The same hook runs during initial typing and stock redraw/scroll, so both paths
must produce byte-identical staged cells.

### Memory budget

The current external English pool uses Super System Card banks `$7C-$7F`.
VWF adds a mission-specific descriptor dictionary and may expand the
translation allocation downward as required. The release builder must compute
the exact per-mission bank count rather than hard-code a global maximum.

Translation storage and load-time caches must have disjoint, manifest-declared
Card-RAM ownership. No cache optimization may silently reuse a translation
bank.

### Timing

The 79 records with meaningful controls use frozen explicit English phrase
anchors. VWF wrapping may change line breaks but may not move a semantic
control across its approved fragment boundary.

The historical proportional `2F` placement helper is diagnostic-only and is
not permitted in release builds.

### Release gates

VWF promotion requires:

- compiler round-trip tests;
- every compiled line fits the 176-pixel / 11-cell field;
- dictionary/token bounds validated for every mission;
- fixed renderer fallback remains functional;
- initial render and stock redraw produce identical staged cells;
- page scrolling preserves VWF tokens;
- controls between VWF segments remain byte-identical;
- representative runtime proof in Mission 0 and at least one later overlay;
- full Mission 0-8 playthrough before release.
