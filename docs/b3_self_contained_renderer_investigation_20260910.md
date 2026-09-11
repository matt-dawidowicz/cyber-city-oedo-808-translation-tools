# B3 self-contained renderer / space proof

Status date: 2026-09-10  
Baseline: `0fb5dd8bcc3be5a48eae11254cd891782d3b2055`  
Branch: `b3/self-contained-renderer-space-proof-20260910`

## Scope and hard constraints

This phase remains evidence-driven. It must not produce another speculative
runtime BIN.

The release architecture is **stock Japanese System Card 3.0 + patched game
only**. A patched BIOS or patched System Card may be consulted as architectural
reference material, but it is not an acceptable dependency. Global in-band
escape markers are permanently rejected: the earlier `FF` and `FF 00`
experiments collided with unrelated loaded data and corrupted runtime state.

Load-time optimization is a separate campaign and is intentionally out of scope
here.

## H_BARTEN live-runtime proof

The 2026-09-10 Mesen session closes several B2/B2.5 gates and supersedes earlier
allocation assumptions. The complete machine-readable observation is in
`docs/evidence/h_barten_live_runtime_20260910.json`.

The visible same-size test proves that the opening bartender is `H_BARTEN`, not
the larger `BARTEN1` copy. At the live parser stop, the record marker is at
`$C690`, text begins at `$C692`, and direct-page bytes `$207F/$2080 = 92 C6`
point to the same `$C692` address. `MPR6=$84` therefore identifies physical bank
`$84` for the active stream window.

The ordinary path reaches the stock cell renderer at `$5915`. A captured glyph
pair was `$2002/$2003 = 60 82`, i.e. Shift-JIS `$8260` (`Ａ`). The path then
reaches stock System Card `EX_GETFNT` at `$E060`. A later captured call used
`$F8/$F9 = 61 82` (`Ｂ`), `$FA/$FB = 6C 4C` (destination `$4C6C`), and `$FF=00`
(16x16 font). `$4C6C-$4C8B` changes from an observed empty state to the generated
32-byte glyph bitmap, then execution returns to game code at approximately
`$56C3` for the game's own bitmap-processing/rendering path.

## Allocation audit

No candidate is promoted to safe storage merely because it is zero-filled or
lies inside a loaded image.

| Candidate | Static evidence | Live evidence | Status | Reason |
|---|---|---|---|---|
| `$9F1B-$9FFF` | Historically zero-filled in the Mission 0 image | R/W/X watch fired on a live read from System Card code near `$F4FC`: `LDA ($FA) [$9F1B] = $00` | **FORBIDDEN** | Runtime-used, apparently by an ADPCM-related transfer path. Never inject here. |
| Extend `H_BARTEN` from `$0080` to `$0800` | Directory declares only `$0080` bytes | Extended-load experiment glitched/corrupted runtime | **FORBIDDEN AS A STRATEGY** | Crosses the resource's proven extent and changes loader lifetime/ownership assumptions. |
| Bytes inside the existing `H_BARTEN` `$0080` extent | Resource ownership is known | No free tail or lifetime has been proven | **UNPROVEN** | Internal zeros/padding are not automatically free; references and lifetime must be traced. |
| Historical `$A300` / `$A800` module padding | Inside the loaded Mission 0 image; old experiment found homogeneous padding | No execution/read/write non-use proof for the full scene lifetime | **UNPROVEN / DO NOT USE** | Being inside the image is stronger than arbitrary disc padding, but still not ownership. |
| Persistent RAM | General RAM exists | No candidate range has a proven owner/lifetime compatible with the renderer | **UNPROVEN** | Must be demonstrated with allocation/loader semantics and live watches. |
| Reclaimed bytes in existing renderer/parser code | Known code path at `$9543`, `$5915`, and near `$56C0` | Exact live path is now known | **PROMISING, NOT YET ALLOCATED** | Requires control-flow boundary proof and a byte budget before any replacement can be justified. |

The negative result is useful: the next renderer cannot be designed around a
speculative cave. Storage proof is an explicit prerequisite rather than
something inferred after a patch happens to boot.

## Mission 0 capacity under one-byte English

The historical fullwidth result was dominated by the cost of two-byte Shift-JIS
Latin. The recalculation in
`docs/evidence/mission0_one_byte_capacity_20260910.json` treats English as one
byte per normalized ASCII character while retaining each record's existing
`source_bytes` as its local capacity.

The exact historical `497/502` cohort is not reproducible from current main or
the recovered project artifacts, so this analysis does **not** pretend to
replace that denominator exactly. It does establish the direction and magnitude
of the correction using two reproducible workbooks.

In the older review workbook, 454 of 821 valid translated Mission 0 records fit
their local source-byte budgets under the one-byte projection. Aggregate
capacity is almost neutral (`44,490` source bytes versus `44,732` projected
English bytes), but dialogue is short by `3,541` bytes while auxiliary text has
`3,299` bytes of surplus. Those pools cannot be combined without independent
relocation proof.

The current master script is somewhat more verbose: 439 of 851 Mission 0
translations fit locally, with an aggregate deficit of `1,781` bytes. Dialogue
remains the pressure point (`-3,998` bytes); auxiliary text remains net positive
(`+2,217` bytes).

**Conclusion:** one-byte English dramatically reduces the local storage problem,
but parser/rendering semantics and safe relocation remain the dominant
engineering work.

## Typography architecture decision after disc-capacity review

The project no longer optimizes the production renderer around eliminating a
roughly 1.5 KiB font table. Disc bytes are cheap at this scale; live RAM and
owned executable space are not.

The production direction is therefore a **self-contained embedded-font text
subsystem**. The detailed contract is in
`docs/text_engine_v1_design_20260910.md`, with corpus evidence in
`docs/evidence/english_typography_repertoire_20260910.json` and build-time
helpers in `cyber_oedo.text.typography`.

The current English corpus contains 91 distinct characters across 2,914 working
translations. The initial production font contract deliberately contains all 95
printable ASCII characters plus eight corpus-required extensions (`¥`, en dash,
em dash, curly single/double quotes, and the solid square), for **103 glyphs**.

At 8x16 and one bit per pixel, that is only **1,648 bytes per complete font** or
**4,944 bytes for three complete fonts**. The engine should therefore permit at
least three logical roles:

- `dialogue`: readable mixed-case conversation and narration;
- `ui`: condensed menus, labels, database/news text; and
- `display`: headings, terminals, and stylized emphasis.

These roles need not be resident simultaneously. The eventual loader should be
free to load the font required by the active scene/module.

### First runtime typography target

The first playable target remains conservative at the renderer boundary:

1. Enter English through a **record-/handler-/resource-local** selector, never a
   global in-band marker.
2. Load one 103-glyph dialogue font into a proven-owned RAM range.
3. Store English text as one-byte characters under a context-local codec whose
   control-byte namespace is independently proven.
4. Compose two 8x16 glyphs into the 32-byte 16x16 cell-buffer shape observed at
   `$4C6C-$4C8B`.
5. Resume the game's existing post-font bitmap path around `$56C3`, reusing the
   stock cell/VDC machinery where possible.
6. Preserve the stock 11-cell cursor initially, yielding up to 22 fixed-width
   English characters per line without introducing half-cell cursor state.

After this path survives redraw, menus, and scene exit, build-time pixel metrics
can support proportional advances. A later renderer may maintain a pixel cursor
or compose an entire line/window in scratch graphics memory. That is a second
runtime milestone, not a prerequisite for the first proof.

## Retained fontless fallback / diagnostic route

The live `$E060 -> $4C6C -> ~$56C3` path is still useful. `EX_GETFNT` can serve
as a source of reference glyphs, a diagnostic comparison for the 32-byte buffer
format, or a fallback for characters absent from a loaded custom font.

It is no longer the preferred production route solely to save 1,520 bytes of
font data. The earlier idea of mapping English to fullwidth Shift-JIS, calling
`EX_GETFNT`, cropping each 16x16 glyph, and composing two halves remains a valid
experiment if it proves simpler or cheaper in live RAM than the embedded-font
path.

The `dshadoff/SYSCARD_Translatefont` project remains reference material only. A
modified System Card is explicitly outside this project's release architecture.

## Why a transient English-mode flag is insufficient

The stock redraw path revisits persisted dialogue cells, not only the newest
character. An ephemeral global flag can therefore reinterpret old cells or stock
Japanese blanks during redraw. The English/Japanese distinction must be
recoverable from stable record/cell state or from a scene-local state whose
lifetime is independently proven.

This makes the parser-selector problem as important as the glyph compositor.
The selector should be attached to a known resource/handler context, not encoded
as a magic byte sequence that can occur elsewhere.

## Evidence needed before any runtime BIN

The next phase should gather evidence, not patch code:

1. Trace reads/writes of `$4C6C-$4CAB` and capture the buffer after `EX_GETFNT`
   and through the later `$56xx/$4Exx` processing. This proves the interface a
   custom font renderer must feed; it no longer exists solely to derive a crop
   rule.
2. Disassemble and bound the exact game routine surrounding the `$56C0` font
   call and its post-call processing.
3. Map the Mission 0 loader and RAM-bank lifecycle around entering the bar,
   dialogue, redraw/menu activity, and scene exit. The goal is a deliberately
   owned resident range for renderer/font data, not another code cave.
4. Trace the `H_BARTEN` descriptor/stream-install path and its lifetime so a
   record-/handler-/resource-local one-byte selector can be chosen without
   changing unrelated bytecode.
5. For every proposed code or RAM range, combine static loader/reference
   analysis with live read/write/execute watches across the complete bartender
   conversation and transition out of the scene.

### Runtime-mutation gate

Do **not** build another renderer BIN until all of these are true:

- an executable/data location is proven owned for the adapter/font's full active
  lifetime;
- a deliberate loader path or equivalent already-owned residency mechanism is
  proven;
- a record-/handler-/resource-local one-byte selector is proven collision-free
  and redraw-safe; and
- the 32-byte 16x16 glyph-buffer interface and downstream game bitmap path are
  bounded well enough that an embedded 8x16 pair compositor can feed them
  without corrupting unrelated state.

A stock-`EX_GETFNT` 16x16-to-8x16 transform is now **optional**, not a mandatory
production gate. It is required only if the fontless fallback route is selected.

Until these gates close, B3 remains an evidence and architecture phase.
