# Mission 0 packed-English renderer proof

Status: source-guarded implementation complete; emulator certification pending.

## Purpose

This is the first runtime activation of the final English font architecture. It
is deliberately narrower than the retired July wide-text experiment.

The dialogue parser is untouched.

Private English text is encoded as ordinary two-byte glyphs using the reserved
Shift-JIS lead range `F0-FC`. The stock parser therefore advances through
English with its normal glyph path. Only the font service call at logical
`$56C0` is intercepted.

## Proven stock path

Mission 0-B stock code around the hook is:

```text
56AB  LDA $02
56AD  STA $F8
56AF  LDA $03
56B1  STA $F9
...
56BF  SEI
56C0  JSR $E060
56C3  CLI
56C4  LDA #$00
...
56CE  JSR $4E86
```

The redraw loop stores the first glyph byte in `$03` and the second in
`$02`, so at the hook:

- `$F9` = Shift-JIS/private lead byte;
- `$F8` = Shift-JIS/private trail byte.

For non-private leads the new hook calls the exact original System Card
`EX_GETFNT` service and returns.

For private leads it writes the 32-byte `$4C6C` staging cell itself and
returns to `$56C3`. The existing `$4E86` transform, VDC upload, BAT write,
text-grid redraw, cursor advance, scroll, timing, and page handling remain
untouched.

## Runtime storage

The initial proof is intentionally limited to the Mission 0-B resident overlay.

Authenticated payload base:

```text
0x00131800
```

Candidate logical region:

```text
$A300-$BFFF
```

Source contract:

| Logical range | Original bytes |
|---|---|
| `$A300-$A7FF` | exactly `00` |
| `$A800-$BFFF` | exactly `E5` |

The complete 7,424-byte region has SHA-256:

```text
c4b3d9d150441e0fb914e0d8f8ffaf0e73c6b7e7037759fff4eb8a7c762fe18b
```

This is stronger than merely finding a low-entropy run, but it is still scoped
as a Mission 0 runtime proof. Later overlays do not inherit this ownership
claim.

## Final-master sizing

The 2026-09-24 final localization master produces:

- 1,522 distinct packed character pairs;
- 91 display glyphs;
- 3,044 bytes of pair-table data;
- 1,456 bytes of 8x16 one-bit atlas data.

With the current runtime:

| Component | Logical range |
|---|---|
| decoder/compositor | `$A300-$A449` |
| pair table | `$A500-$B0E3` |
| glyph atlas | `$B100-$B6AF` |

The used resident range therefore ends at `$B6B0`, leaving `$950` bytes
before `$C000`.

## Runtime algorithm

For lead `F0-FC`:

1. convert the lead to `0..12`;
2. multiply by 188;
3. convert trail `40-7E,80-FC` to `0..187`;
4. add the trail index;
5. reject indexes beyond the active pair dictionary;
6. multiply the pair index by two;
7. load left/right one-byte glyph IDs from the pair table;
8. use those IDs as X/Y indexes into each of the sixteen row-major atlas rows;
9. write left/right bytes to `$4C6C-$4C8B`;
10. restore X/Y and return.

Malformed/out-of-range private indexes render `??`.

## First visual proof

The first proof modifies one exact same-size field:

- payload offset: `0x00145892`
- Japanese: `バーテン「いらっしゃいませ」`
- English: `Bartender: ‘Welcome.’`
- source field: 28 bytes
- packed English: 22 bytes
- remaining six bytes: stock-ignored `80`

The existing following null terminator and surrounding command stream are not
moved.

## Authenticated payload test

The implementation was validated against the supplied Track 2 payload:

- size: 84,375,552 bytes
- SHA-256:
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`

All five proof patch sources matched:

1. font-fetch hook;
2. runtime code storage;
3. pair-table storage;
4. atlas storage;
5. bartender source field.

The resulting proof touches relative Track 2 sectors:

```text
621, 631, 632, 633, 651
```

## Live certification

Use `tools/mesen_packed_english_capture.lua`.

A successful packed-glyph event must show:

```text
$56C0 -> $A300 -> $56C3
```

with:

- MPRs stable across the call;
- `$F9` in `F0-FC`;
- a valid private trail in `$F8`;
- a populated 32-byte `$4C6C` staging cell after return;
- normal continuation through the stock renderer;
- readable bartender English;
- Japanese fallback still working for non-private glyphs.

The Mesen check is the remaining gate before this Mission 0 renderer proof is
called runtime-certified.
