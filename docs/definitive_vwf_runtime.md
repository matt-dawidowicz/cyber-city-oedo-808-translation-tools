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

Each mission first owns a deduplicated dictionary of VWF cell descriptors. A
descriptor records the ordered glyph IDs needed to reconstruct one 16-pixel
cell. The build-time compiler rejects a cell whose proportional glyph advances
exceed 16 pixels.

For runtime use, every unique descriptor is then pre-rendered into the stock
32-byte 16x16 font-staging format. Tokens index those ready-to-copy cells
directly. This moves proportional composition out of the HuC6280 hot path:
initial typing and redraw both consume the same byte-identical staged cell.

### Runtime compositor

The font hook distinguishes three cases from the stored cell bytes:

1. stock Japanese cell -> BIOS font path;
2. fixed native-English cell -> existing 8x16 compositor;
3. VWF token -> VWF descriptor lookup and 16x16 composition.

The implemented VWF hot path:

1. decodes the cell token;
2. maps the corresponding Card-RAM bank at $A000 through MPR5;
3. converts the token low byte to a 32-byte aligned source address;
4. copies the pre-rendered cell directly into the existing $4C6C font staging
   buffer;
5. restores MPR5 and temporary direct-page state;
6. returns to the stock transform/BAT path.

The same hook runs during initial typing and stock redraw/scroll, so both paths
must produce byte-identical staged cells.

### Memory budget

The current external English stream pool uses Super System Card banks
`$7C-$7F`. Pre-rendered VWF cells reserve `$70-$7B`: twelve 8 KiB banks,
256 staged cells per bank, for a runtime capacity of 3,072 unique cells per
mission. The token high byte selects the bank and the low byte selects the
32-byte cell within that bank.

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
