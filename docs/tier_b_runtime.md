# Tier B runtime architecture

Tier B owns HuC6280 runtime-engine proof and any later source-guarded engine
changes. Tier A remains the authoritative host-side parser, resource,
inventory, compiler, and disc-verification layer.

## B1: dialogue-interpreter proof

The first Tier B milestone is read-only. It must establish the live code path
before any new renderer or relocation hook is designed.

The authenticated Mission 0 module maps logical addresses below `$A000` from
Track 2 payload base `0x00131800`. The dialogue interpreter begins at `$9543`.
The source-guarded B1 model records the following code regions:

| CPU address | Role |
|---:|---|
| `$9543` | stream read/advance and zero terminator dispatch |
| `$958F` | opcode `3D` handler |
| `$6694` | one-byte indexed-record address calculation |
| `$960F` | null-terminated indexed-field glyph loop |
| `$5915` | stock dialogue glyph-cell renderer |
| `$9F11/$9F14` | stream read/advance helpers |
| `$9F1B-$9FFF` | historical zero-filled Stage 1 region |

The last region remains **unowned**. Zero fill is evidence about bytes, not
proof that the loader, another overlay, save state, or later runtime path never
uses the region.

## Opcode `3D`

Static execution at `$958F` establishes this Mission 0 behavior:

1. consume two operand bytes;
2. read and discard operand 0;
3. place operand 1 in zero page `$00`;
4. call `$6694`, which computes
   `$A400 + ((operand1 - 1) & $FF) * $20`;
5. inspect byte `$1A` of the selected 32-byte record;
6. render from record offset `$00` when that byte is nonzero, otherwise add
   `$0D` and render the alternate field; and
7. return to the dialogue stream.

`$960F` renders the selected field as two-byte glyph pairs until its first byte
is zero, calling the stock cell renderer at `$5915` for each pair.

This establishes `3D` as an indexed record-field text insertion command. The
higher-level identity of the `$A400` table and the meaning of its state byte
still require loader/runtime correlation before they receive game-facing names.

## Runtime proof command

Run:

```text
cyber-oedo prove-dialogue-runtime track02_mode1_2048.bin \
  --dialogue dialogue.tsv --output tier_b_runtime.json
```

The command checks the authenticated Track 2 SHA-256, validates every B1 code
window byte-for-byte, reports the historical zero region without promoting its
ownership, and correlates `3D` operand pairs from a Tier-A dialogue TSV.

## Gates before B2

B2 may design a record-local selector or another engine modification only
after these remaining runtime facts are captured in an emulator trace:

- MPR/bank mapping at `$9543` and `$958F`;
- the live `$7F/$80` stream pointer for representative dialogue;
- the loaded source and ownership of the `$A400` indexed table;
- the selected record and state byte for at least two distinct `3D` operands;
- glyph buffer/VDC destination through `$5915` and BIOS font service; and
- evidence that any proposed injection storage is owned for the full lifetime
  of the hook.

No global escape marker is permitted. The failed Stage 1 experiments already
showed that apparent marker absence inside extracted dialogue does not imply
runtime-global safety.
