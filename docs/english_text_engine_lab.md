# English text-engine lab

## Purpose and isolation

This worktree is the experimental renderer branch. It starts at stock-renderer
commit `1ed7b8c` and is intentionally separate from the maintained
`agent/hardened-toolkit` checkout and its playable CloneCD build.

No game image is produced by this branch until the runtime-proof gates below
are satisfied. The full translation corpus is maintained separately in
`deliverables/cyber-city-oedo-808-full-text-corpus-2026-07-28/`; translators
should author natural English without the stock renderer's 11-cell limit.

## Target capability

The target is an explicit English escape mode that:

1. stores Latin text in one-byte codes rather than two-byte Shift-JIS;
2. renders a readable fixed-pitch 8x16 ASCII glyph at each half-cell;
3. gives the existing dialogue window 22 English columns where it currently
   gives 11 native 16x16 cells; and
4. preserves the original Shift-JIS/control path for Japanese, item logic,
   pointers, timing commands, page commands, and untouched records.

This is not the archived compact experiment. That experiment reduced script
storage pressure but retained one 16x16 display glyph per cell, so it did not
establish the wider English layout needed for accurate prose.

## Static evidence to revalidate

The archived experiment named these Mission 0 candidates. They are hypotheses
until confirmed against the authenticated payload and live execution:

| Candidate | Historical CPU address | Required proof |
|---|---:|---|
| parser decision | `$95D4` | execution reaches it for both Japanese and dialogue text |
| glyph path | `$56C0` | receives one decoded printable glyph before VRAM upload |
| line advance | `$58CE` | governs the visible dialogue line boundary |
| stock continuation | `$95D8` | preserves Japanese/control behavior when escape mode is inactive |
| font BIOS call | `$E060` | reads/writes the font buffer used by this scene |
| historical code cave | `$9F1B`, 229 bytes | code, data, and reachability ownership—not only unused-looking bytes |

Static disassembly against the authenticated payload confirms the addresses
and shows the parser's current split: `$95D4` compares the stream byte with
`$80`; values below or equal to `$80` jump back to the stock parser at
`$9543`, while a larger value is saved as a Shift-JIS lead byte, delayed, reads
the trail through `$9F11`/`$9F14`, and calls the glyph path at `$5915`.
`$56C0` immediately calls BIOS font service `$E060`. The historical cave is
zero-filled, but that is not ownership proof. The proposed `FF`/`FE` escape
markers are absent from all 3,799 extracted structured dialogue records; they
remain provisional until the runtime trace proves that no unobserved control
or resource consumer reserves them.

## Runtime trace gates

Before writing an injected routine, capture a Mission 0 trace while showing a
normal dialogue line and the item verb screen. Record:

1. program counter, bank, and stream byte at parser entry;
2. all branch outcomes for bytes below `0x80`, Shift-JIS lead bytes, controls,
   and an experimentally injected escape value in an offline copy;
3. font-buffer address, glyph bytes, VRAM destination, X position, and line
   counter for one glyph;
4. whether a 16-pixel cell is one tile or a paired tile upload;
5. window clear, page/input handling, timing, and cursor state; and
6. entry and draw path of `INVENTRY`, so its verb labels can be decoded rather
   than guessed from raw disc bytes.

The trace must be behavior-neutral. An emulator debugger breakpoint/logpoint
or a temporary ROM trace build may observe these values, but no compact-font
patch is allowed in the playable profile.

## Implementation sequence

1. Revalidate module mapping and every hook guard against the source payload.
2. Write a reproducible 8x16 ASCII font asset and a host-side encoder.
3. Add an escape parser whose inactive path is byte-identical to stock.
4. Replace the glyph-upload path only while the escape mode flag is set.
5. Advance X by eight pixels in escape mode; retain the original 16-pixel
   advance for stock Shift-JIS.
6. Add a 22-column word-wrap/page compiler that preserves observed page and
   timing controls exactly.
7. Test Japanese dialogue, English dialogue, mixed controls, item screens,
   page turn, scene transition, audio, save, restart, and reload in an
   emulator.
8. Only then create a separately named experimental CloneCD build and compare
   every changed sector to its explicit patch plan.

## Stop conditions

Do not insert an engine patch when any hook is only statically inferred, the
code-cave ownership is unproven, the font upload is not traced, an escape byte
collides with an observed control, the 8x16 glyph is unreadable, a page does
not clear/repaint correctly, or save/reload changes behavior.
