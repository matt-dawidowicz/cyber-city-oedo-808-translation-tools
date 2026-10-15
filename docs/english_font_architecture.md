# English font and packed-glyph architecture

## Goal

Replace difficult-to-read fullwidth English with a deliberate high-legibility
English typography system without repeating the failed global escape-marker
experiment.

Natural English comes first. Original Japanese byte capacity is not a prose
constraint simply because the game is old. This is a CD game, and expanded
resources can be engineered where ownership and loading are proven.

Disc space is abundant. RAM, VRAM, pointer windows, and overlay lifetime remain
real constraints.

## Why the old escape design stays retired

The Stage-1 experiment switched renderer behavior when raw marker bytes such as
FF or FF 00 appeared in loaded data. Those sequences also occurred naturally in
unrelated state/data and produced crashes and renderer corruption.

No future English design may depend on a global low-level escape signature.

## Private two-byte glyph namespace

The common dialogue parser already provides a safe structural distinction:
known low bytes are controls/operands, while a first byte above 80 is consumed
with the following byte as one glyph.

The final English design reserves Shift-JIS user-defined lead bytes F0-FC with
valid trail bytes 40-7E and 80-FC. That provides 13 x 188 = 2,444 private
tokens.

A character-by-character audit of the Japanese source represented in the final
localization workbook found no source character whose Shift-JIS encoding begins
with F0-FC.

## Two characters per stock cell

One private token indexes a pair of English display glyph IDs.

At render time:

1. the stock parser consumes the private token as one normal two-byte glyph;
2. the font-fetch hook recognizes lead F0-FC;
3. the token is converted to a zero-based pair-table index;
4. the pair table yields two one-byte glyph IDs;
5. two 8x16 bitmap glyphs are composed side by side into one 16x16 cell;
6. those 16 rows x 2 bytes are written directly into the existing $4C6C
   32-byte System Card font staging buffer;
7. the existing $4E86 transform, VDC upload, BAT write, cursor, grid, scroll,
   and window code continues unchanged.

Normal Japanese/Shift-JIS glyphs continue through System Card EX_GETFNT.

This keeps the useful two-character idea from the old 8x16 experiment without
an unsafe parser escape mode.

## Effective line width

The stock dialogue engine has 11 ordinary 16x16 cells per line. At two English
glyphs per cell, that is 22 English characters per normal line.

The cell grid remains 3 x 12 x 3 bytes. Scrolling and redraw need no half-tile
cursor arithmetic because the runtime still sees one cell per pair.

## Pair dictionary

The build compiler scans final visible English and creates a deterministic
dictionary of non-overlapping character pairs.

The 2026-09-24 final-pass workbook uses 1,522 distinct pairs, leaving 922 free
private tokens. Its pair table requires 3,058 bytes.

Each pair-table entry is only two one-byte glyph IDs.

## Glyph repertoire

The current final-pass workbook uses 91 distinct display characters. Non-ASCII
characters are limited to smart quotation/apostrophe marks, em/en dash,
ellipsis, yen sign, and a square/status glyph.

A one-byte glyph ID therefore has ample space. At one bit per pixel, one 8x16
glyph is 16 bytes, so even roughly 100 glyphs are only about 1.6 KiB before
runtime conversion/staging overhead.

The repository should contain the codec/importer and source hash/metrics, not a
redistributed proprietary font binary. A supplied or approved font source can
be rasterized deterministically during the build.

## Visual specification

### Dialogue

Use a high-legibility 8x16 design with strong x-height, clear lowercase,
distinct I/l/1 and O/0, generous counters, and enough stroke weight to survive
CRT/composite softness. Internal raster tests favor a heavy mono/sans face at
roughly 13-14 px over thin terminal faces; a Noto Sans Mono SemiBold-class
raster is the current visual reference, not a redistributed build dependency.
It should be comfortable for thousands of lines rather than merely look
futuristic in a screenshot.

### Menus

Menus may use the same atlas or a slightly heavier screen-local variant. Command
choices must be immediately legible.

### Opening terminal/database

Use a crisp monospaced terminal presentation. Uppercase readouts are intentional
here and should look like a designed boot/database interface.

### Titles and true graphics

Do not force every screen through the dialogue font. Mission titles, logos, and
other proven graphics-backed presentation can use screen-specific pipelines.

## CD expansion policy

Do not use the two-character renderer as an excuse to preserve original
Japanese byte budgets. Packing improves display geometry; it does not define
storage ownership.

For longer English resources, update or relocate the owning resource only after
proving every pointer/reference, exact CD source extent, loader byte/sector
length, RAM destination extent/lifetime, bank/address constraints, resident
overlap, and save/reload/scene-transition behavior.

Where those contracts are proven, adding CD sectors is acceptable.

## Activation gates

Before enabling the renderer in a playable build:

1. source-guard the font-fetch hook in every common text overlay;
2. prove collision-free runtime storage for decoder code, pair table, and atlas,
   or load them as an explicitly owned resource;
3. verify no translated stream uses private tokens before the hook is resident;
4. verify stock Japanese fallback;
5. verify 22-character wrapping, three-row scroll, punctuation, input skip, and
   voice-sync controls;
6. replay Mission 0 and representative later missions under Mesen with MPR
   logging;
7. verify information screens, menus, save UI, ending, and credits separately;
8. compare the final disc-sector mutation footprint against the build manifest.

Until these gates pass, this is a tested compiler/runtime design, not permission
to patch arbitrary empty-looking bytes.
