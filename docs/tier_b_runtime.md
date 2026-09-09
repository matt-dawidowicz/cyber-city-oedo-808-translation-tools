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

## B2 static loader and state proof

The authenticated Mission 0 startup path now resolves the source and shape of
the `$A400` table without relying on an emulator assumption.

At `$64CB`, the game prepares a transfer whose destination is `$A400`, whose
source is absolute disc LBA `$107D`, and whose byte count is `$0301`. The
transfer is passed through `$6EA0`; its full-sector path populates the System
Card argument block and calls the CD-ROM BIOS entry at `$E009`.

Track 2 begins at absolute LBA `$0E06`, so source LBA `$107D` resolves to:

- Track-2-relative sector `$0277`;
- payload offset `0x0013B800`; and
- exactly 769 source bytes.

Those bytes are structurally **24 records × 32 bytes plus one trailing byte**.
Each record contains two 13-byte null-terminated Shift-JIS text slots at
offsets `$00` and `$0D`, followed by runtime-state bytes. The exact 769-byte
source region is guarded by SHA-256 rather than committed to the repository.

The state selector at record byte `$1A` is also no longer an isolated
observation. The outer script dispatch table maps opcode `$2F` to `$94A4`;
that handler consumes one record index and calls `$66F9`, which computes the
same `$A400 + (index - 1) * $20` address and writes `$FF` at offset `$1A`.
The `3D` handler tests that byte to choose the primary field at `$00` or the
alternate field at `$0D`.

For the authenticated Mission 0 source, record 6 demonstrates why this
matters: its two fields are a specific identity and a generic descriptor, and
its initial `$1A` value is zero. That is strong static evidence that this
field-selection state supports discovery/identification behavior. A live trace
is still required before assigning the same semantic meaning to every record
and every later mission.

## Runtime proof command

Run:

```text
cyber-oedo prove-dialogue-runtime track02_mode1_2048.bin \
  --dialogue dialogue.tsv --output tier_b_runtime.json
```

The command checks the authenticated Track 2 SHA-256, validates every B1/B2
static code window byte-for-byte, authenticates the Mission 0 indexed-table
source, reports the historical zero region without promoting its ownership,
and correlates `3D` operand pairs from a Tier-A dialogue TSV.

## Gates before Tier-B mutation

A record-local selector or another engine modification may be designed only
after these remaining live facts are captured in an emulator trace:

- MPR/bank mapping at `$9543` and `$958F`;
- the live `$7F/$80` stream pointer for representative dialogue;
- confirmation that `$A400` remains owned for the relevant scene lifetime;
- the selected record and state byte for at least two distinct `3D` operands;
- glyph buffer/VDC destination through `$5915` and BIOS font service; and
- evidence that any proposed injection storage is owned for the full lifetime
  of the hook.

No global escape marker is permitted. The failed Stage 1 experiments already
showed that apparent marker absence inside extracted dialogue does not imply
runtime-global safety.
