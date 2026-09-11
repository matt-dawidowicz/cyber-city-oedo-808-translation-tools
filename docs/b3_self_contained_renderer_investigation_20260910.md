# B3 self-contained renderer / space proof

Status date: 2026-09-10  
Baseline: `0fb5dd8bcc3be5a48eae11254cd891782d3b2055`  
Branch: `b3/self-contained-renderer-space-proof-20260910`

## Scope and hard constraints

This phase is analysis-only. It must not produce another speculative runtime BIN.

The release architecture is **stock Japanese System Card 3.0 + patched game only**. A patched BIOS or patched System Card may be consulted as an architectural reference, but it is not an acceptable dependency. Global in-band escape markers are also permanently rejected: the earlier `FF` and `FF 00` experiments collided with unrelated loaded data and corrupted runtime state.

Load-time optimization is a separate campaign and is intentionally out of scope here.

## H_BARTEN live-runtime proof

The 2026-09-10 Mesen session closes several B2/B2.5 gates and supersedes earlier allocation assumptions. The complete machine-readable observation is in `docs/evidence/h_barten_live_runtime_20260910.json`.

The visible same-size test proves that the opening bartender is `H_BARTEN`, not the larger `BARTEN1` copy. At the live parser stop, the record marker is at `$C690`, text begins at `$C692`, and direct-page bytes `$207F/$2080 = 92 C6` point to the same `$C692` address. `MPR6=$84` therefore identifies physical bank `$84` for the active stream window.

The ordinary path reaches the stock cell renderer at `$5915`. A captured glyph pair was `$2002/$2003 = 60 82`, i.e. Shift-JIS `$8260` (`Ａ`). The path then reaches stock System Card `EX_GETFNT` at `$E060`. A later captured call used `$F8/$F9 = 61 82` (`Ｂ`), `$FA/$FB = 6C 4C` (destination `$4C6C`), and `$FF=00` (16x16 font). `$4C6C-$4C8B` changes from an observed empty state to the generated 32-byte glyph bitmap, then execution returns to game code at approximately `$56C3` for the game's own bitmap-processing/rendering path.

## Allocation audit

No candidate is promoted to safe storage merely because it is zero-filled or lies inside a loaded image.

| Candidate | Static evidence | Live evidence | Status | Reason |
|---|---|---|---|---|
| `$9F1B-$9FFF` | Historically zero-filled in the Mission 0 image | R/W/X watch fired on a live read from System Card code near `$F4FC`: `LDA ($FA) [$9F1B] = $00` | **FORBIDDEN** | Runtime-used, apparently by an ADPCM-related transfer path. Never inject here. |
| Extend `H_BARTEN` from `$0080` to `$0800` | Directory declares only `$0080` bytes | Extended-load experiment glitched/corrupted runtime | **FORBIDDEN AS A STRATEGY** | Crosses the resource's proven extent and changes loader lifetime/ownership assumptions. |
| Bytes inside the existing `H_BARTEN` `$0080` extent | Resource ownership is known | No free tail or lifetime has been proven | **UNPROVEN** | Internal zeros/padding are not automatically free; references and lifetime must be traced. |
| Historical `$A300` / `$A800` module padding | Inside the loaded Mission 0 image; old experiment found homogeneous padding | No execution/read/write non-use proof for the full scene lifetime | **UNPROVEN / DO NOT USE** | Being inside the image is stronger than arbitrary disc padding, but still not ownership. |
| Persistent RAM | General RAM exists | No candidate range has a proven owner/lifetime compatible with the renderer | **UNPROVEN** | Must be demonstrated with allocation/loader semantics and live watches. |
| Reclaimed bytes in existing renderer/parser code | Known code path at `$9543`, `$5915`, and near `$56C0` | Exact live path is now known | **PROMISING, NOT YET ALLOCATED** | Requires control-flow boundary proof and a byte budget before any replacement can be justified. |

The negative result is useful: the next renderer cannot be designed around a speculative cave. Storage proof is now an explicit prerequisite rather than something inferred after a patch happens to boot.

## Mission 0 capacity under one-byte English

The historical fullwidth result was dominated by the cost of two-byte Shift-JIS Latin. The recalculation in `docs/evidence/mission0_one_byte_capacity_20260910.json` treats English as one byte per normalized ASCII character while retaining each record's existing `source_bytes` as its local capacity.

The exact historical `497/502` cohort is not reproducible from current main or the recovered project artifacts, so this analysis does **not** pretend to replace that denominator exactly. It does establish the direction and magnitude of the correction using two reproducible workbooks.

In the older review workbook, 454 of 821 valid translated Mission 0 records fit their local source-byte budgets under the one-byte projection, versus only a small minority under the old two-byte/fullwidth model. Aggregate capacity is almost neutral (`44,490` source bytes versus `44,732` projected English bytes), but that aggregate hides an important split: dialogue is short by `3,541` bytes while auxiliary text has `3,299` bytes of surplus. Those pools cannot be combined without independent relocation proof.

The current master script is somewhat more verbose: 439 of 851 Mission 0 translations fit locally, with an aggregate deficit of `1,781` bytes. Dialogue remains the pressure point (`-3,998` bytes); auxiliary text remains net positive (`+2,217` bytes).

**Conclusion:** one-byte English dramatically reduces the storage problem, but it does not eliminate the need for record-local compaction and some proven relocation. Parser/rendering semantics, not raw byte count, are now the dominant engineering problem.

## Preferred fontless compression route

The live `$E060 -> $4C6C -> ~$56C3` path suggests a smaller self-contained renderer than the old embedded-font experiment.

A candidate architecture is:

1. Enter a **record-/handler-local** one-byte English path. Do not use an in-band global marker.
2. Persist two one-byte English characters in one existing 16x16 dialogue cell so the stock 11-cell line can represent 22 English characters without half-tile cursor state.
3. For each English character, map the byte to a fullwidth Shift-JIS Latin glyph supported by the stock Japanese System Card. Uppercase letters and digits can be mapped arithmetically; punctuation can use a very small explicit map.
4. Call stock `EX_GETFNT` at `$E060` with destination `$4C6C` and `$FF=00` to obtain the 16x16 source glyph.
5. Post-process that 32-byte bitmap into one normalized 8-pixel-wide row stream. The exact crop/shift rule is **not yet proven** and must be derived from live bitmap captures because stock Latin has baseline/width inconsistencies.
6. Generate the second character the same way and compose its 8-pixel rows into the opposite half of the existing 32-byte cell buffer.
7. Resume the game's existing post-`$E060` bitmap path around `$56C3` and reuse as much of the `$56xx` / `$4Exx` processing and `$5915` cell-rendering behavior as possible.

This removes the old 1,520-byte 95-glyph embedded 8x16 font table. The required game-side code should therefore be dominated by a small byte-to-SJIS mapper, row compressor/normalizer, pair compositor, and record-local parser selector rather than font assets. No code-size claim is promoted to fact until the routine is actually assembled against a proven-owned destination.

The `dshadoff/SYSCARD_Translatefont` project remains reference material only. Its 8x16 convention confirms that a narrow glyph naturally fits the same 32-byte destination shape by storing one glyph byte plus one zero byte per row, but its modified-System-Card design is explicitly outside this project's release architecture.

## Why a transient English-mode flag is insufficient

The stock redraw path revisits persisted dialogue cells, not only the newest character. An ephemeral global flag can therefore reinterpret old cells or stock Japanese blanks during redraw. The English/Japanese distinction must be recoverable from stable record/cell state or from a scene-local state whose lifetime is independently proven.

This makes the parser-selector problem as important as the glyph compressor. The selector should be attached to a known resource/handler context, not encoded as a magic byte sequence that can occur elsewhere.

## Evidence needed before any runtime BIN

The next phase should gather evidence, not patch code:

1. Capture `$4C6C-$4C8B` immediately after `EX_GETFNT` for several known Latin glyphs (`Ａ`, `Ｂ`, digits, punctuation), then capture the same buffer after the game returns through `$56C3` and later `$56xx/$4Exx` processing.
2. Trace reads/writes of `$4C6C-$4CAB` so the adjacent derived/scratch buffer shape is known rather than inferred from historical experiments.
3. Disassemble and bound the exact game routine surrounding the `$56C0` font call and its post-call processing, then identify whether simplification can reclaim enough **owned executable bytes** for the adapter.
4. Trace the `H_BARTEN` descriptor/stream-install path and its lifetime so a record-/handler-local one-byte selector can be chosen without changing unrelated bytecode.
5. For every proposed code or RAM range, combine static loader/reference analysis with live read/write/execute watches across the complete bartender conversation, menu/redraw activity, and the transition out of the scene.

### Runtime-mutation gate

Do **not** build another renderer BIN until all three are true:

- an executable/storage location is proven owned for the adapter's full lifetime;
- a record-/handler-local one-byte selector is proven not to collide with unrelated data or redraw state; and
- the stock-`EX_GETFNT` 16x16-to-8x16 transform is demonstrated from captured bitmaps and is compatible with the game's existing post-font pipeline.

Until then, B3 remains an evidence and architecture phase.
