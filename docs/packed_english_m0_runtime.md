# Mission 0 packed-English renderer proof

Status: source-guarded implementation complete; emulator certification pending.

## Purpose

This is the first runtime activation of the final English font architecture.
The dialogue parser remains untouched.

Private English text is encoded as ordinary two-byte glyphs using the reserved
Shift-JIS lead range `F0-FC`. The stock parser therefore advances through
English with its normal glyph path. Only the stock System Card font call at
logical `$56C0` is redirected.

## Corrected residency model

The first draft of this proof incorrectly treated disc padding at
`MISSION0_B_PAYLOAD_BASE + $A300` as though it were automatically mapped to
CPU `$A300`. Review caught that error before merge.

The corrected design uses the already-proven indexed-record loader at `$64CB`.

Stock behavior:

```text
source absolute LBA $107D
        ↓  $0301 bytes
RAM $A400
```

The source contains 24 x 32-byte indexed records plus a one-byte trailer.
The patch changes only the loader byte count:

```text
$0301 → $1C00
```

so the same read becomes:

```text
source absolute LBA $107D
        ↓  $1C00 bytes
RAM $A400-$BFFF
```

The original `$0301` bytes are preserved exactly. The existing source tail is:

| Source-relative range | Original content | RAM destination |
|---|---|---|
| `$0000-$0300` | indexed table + trailer | `$A400-$A700` |
| `$0301-$07FF` | exact `00` fill | `$A701-$ABFF` |
| `$0800-$1BFF` | exact `E5` fill | `$AC00-$BFFF` |

The complete original `$1C00` source interval has SHA-256:

```text
a2a62c29b20d87e7bcad28542d670a6446c62ab8d661c49a4d013317a985767f
```

The English runtime begins at RAM `$A800`, corresponding to source-relative
offset `$0400`. It is therefore explicitly installed by the game's own CD
loader rather than inferred from payload coordinates.

Historical Mission 0 Mesen capture also shows MPR5 remaining `$83` throughout
the covered dialogue/load lifecycle and none of the 36 recorded CD reads
targeting `$A000-$BFFF` after initialization. That is useful lifecycle
evidence, but the new proof capture must still watch the runtime range for
unexpected writes before release certification.

## Stock renderer path

Around the hook the stock path is:

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
56C6  STA $4C6A
56C9  LDA #$00
56CB  STA $4C6B
56CE  JSR $4E86
```

The redraw loop stores the first glyph byte in `$03` and the second in
`$02`, so at the hook:

- `$F9` = Shift-JIS/private lead byte;
- `$F8` = Shift-JIS/private trail byte.

The three-byte `JSR $E060` becomes `JSR $A800`.

For a normal Japanese glyph, the new routine calls the original `$E060` BIOS
service and returns. For a private English token it fills the 32-byte
`$4C6C` staging cell directly and returns. Everything from `$56C3` onward
is stock.

## Final-master sizing

The 2026-09-24 final localization master produces:

- 1,522 distinct packed character pairs;
- 91 display glyphs;
- 3,044 bytes of pair-table data;
- 1,456 bytes of 8x16 one-bit atlas data.

Current resident layout:

| Component | RAM range |
|---|---|
| decoder/compositor | `$A800-$A949` |
| pair table | `$AA00-$B5E3` |
| glyph atlas | `$B600-$BBAF` |

The runtime ends at `$BBB0`, leaving `$450` bytes before `$C000`.

## Runtime algorithm

For lead `F0-FC`:

1. convert the lead to `0..12`;
2. multiply by 188;
3. convert trail `40-7E,80-FC` to `0..187`;
4. add the trail index;
5. reject indexes beyond the active pair dictionary;
6. multiply the pair index by two;
7. load left/right one-byte glyph IDs from the pair table;
8. use those IDs as X/Y indexes into each of sixteen row-major atlas rows;
9. write left/right row bytes to `$4C6C-$4C8B`;
10. restore X/Y and return.

Malformed/out-of-range private indexes render `??`.

## First visual proof

The proof modifies one fixed-size field:

- payload offset: `0x00145892`
- Japanese: `バーテン「いらっしゃいませ」`
- English: `Bartender: ‘Welcome.’`
- source field: 28 bytes
- packed English: 22 bytes
- remaining six bytes: stock-ignored `80`

The following null terminator and surrounding command stream do not move.

## Authentication gates

Validation requires both:

1. every individual patch source to match; and
2. the complete unmodified `$1C00` indexed-table-plus-padding interval to
   match its authenticated SHA-256.

Matching only the individual code/data destinations is deliberately
insufficient.

## Live certification

Use `tools/mesen_packed_english_capture.lua`.

A successful packed-glyph event must show:

```text
$56C0 -> $A800 -> $56C3
```

with:

- MPR5 = `$83` at the font hook;
- `$F9` in `F0-FC`;
- a valid private trail in `$F8`;
- a populated 32-byte `$4C6C` staging cell after return;
- the runtime bytes at `$A800-$BBAF` surviving the covered scene lifecycle;
- normal continuation through the stock renderer;
- readable bartender English; and
- stock Japanese fallback still functioning for non-private glyphs.

The Mesen check remains the final gate before this Mission 0 proof is called
runtime-certified.
