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

## B2.5 bank-aware live snapshot validation

The static model is now sufficient to validate a frozen emulator stop without
confusing a reused logical address with the Mission 0 interpreter. The live
snapshot validator requires:

- a 64 KiB logical CPU-memory dump from the stopped emulator;
- `PC`, accumulator `A`, and all eight HuC6280 MPR values;
- `PC == $9593`, the success path after `CMP #$3D`;
- `A == $3D`; and
- MPR4 == `$82`, proving that logical `$9593` maps to the authenticated
  Mission 0 interpreter bank rather than another overlay.

It reads the stream pointer from HuC6280 direct page `$7F/$80`, which appears
at logical `$207F/$2080`, decodes the two live operands, reproduces the `$6694`
record calculation, reads record byte `+$1A`, and reports both text fields and
the field selected by the live state. The report also records the SHA-256 of
the exact 64 KiB memory snapshot so the evidence is self-identifying. No
emulated memory or disc bytes are changed.

Run:

```text
cyber-oedo prove-live-dialogue-snapshot registers.json memory.bin \
  --output live_3d_proof.json
```

The metadata file accepts integer or base-prefixed string values, for example:

```json
{
  "pc": "0x9593",
  "a": "0x3D",
  "mprs": ["0xFF", "0xF8", "0x00", "0x81", "0x82", "0x83", "0x84", "0x00"]
}
```

This does not complete the live gate by itself. It makes the gate reproducible:
a captured stop is either rejected for the wrong PC/opcode/bank or converted
into deterministic evidence for the stream, indexed record, state byte, and
selected field.

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


## Mission 0 stock glyph pipeline

The stock text renderer is now source-guarded through its font and VDC path,
rather than stopping at the cell dispatcher.

At $56AB, the renderer copies the two-byte glyph code from $02/$03 into the
System Card font-service argument block, sets destination $4C6C and mode 0, and
calls EX_GETFNT at $E060. The fetched 16x16 glyph is then transformed by $4E86
from the $4C6C staging area into a second view beginning at $4C8C.

At $570C the game selects VDC MAWR and VWR, then calls $5772 twice to stream
sixteen word pairs from the transformed and original staging views through the
VDC data ports. $4A38 separately computes the BAT/tilemap address from the
caller's cell index and the base in $34/$35, selects MAWR/VWR, and writes the
16-bit cell entry.

The cell dispatcher at $5915 still owns the 11-cell ordinary width and
12-cell punctuation exception. Its $59B7 staging path records the glyph into
the text-grid buffer and uses $2827 with the low joypad bits at $2228 to
shorten per-glyph delay while input is held.

Run:

```text
cyber-oedo prove-text-renderer-runtime track02_mode1_2048.bin \
  --output text_renderer_proof.json
```

This closes the static font-staging and VDC-transfer questions for the
authenticated Mission 0 source. Exact live VRAM/BAT ownership and later-mission
identity remain runtime certification tasks.

## Exploration movement static proof

A separate source-guarded candidate module at Track 2 payload base 0x000A4800
contains a coherent exploration input/movement path.

- $46F2 reads $2228 and normalizes the first active joypad bit to codes 1..8.
- $51E0 stores current and previous input at $276C/$276D.
- $52AA filters codes 1..4 into current/previous movement directions
  $276E/$276F.
- The direction tables encode Left, Down, Right, Up as both signed unit vectors
  and signed 16-pixel projection vectors.
- $2760/$2761 and $2762/$2763 are the 16-bit X/Y pairs read and updated by this
  movement path.
- $2767/$2768 hold the signed per-step X/Y vector.
- $2769 is initialized to $10; $4A9E decrements it and commits the signed unit
  vector to the X/Y pairs.
- $5409/$490A perform the pre-commit map/collision gate.

The older $220C/$2210 observations belong to a distinct tile-scroll path:
that code updates the values at sub-tile resolution and, at 16-pixel
boundaries, draws newly exposed map rows/columns to VRAM. They should therefore
not be used as player-position names.

Run:

```text
cyber-oedo prove-movement-runtime track02_mode1_2048.bin \
  --output movement_static_proof.json
```

The movement report deliberately labels its module identity as statically
self-consistent rather than live-certified. A frozen MPR capture at an active
movement PC is the next gate for assigning the same mapping to individual
scenes and later overlays.

## Gates before Tier-B mutation

A record-local selector or another engine modification may be designed only
after these remaining live facts are captured in an emulator trace:

- MPR/bank mapping at `$9543` and `$958F`;
- the live `$7F/$80` stream pointer for representative dialogue;
- confirmation that `$A400` remains owned for the relevant scene lifetime;
- the selected record and state byte for at least two distinct `3D` operands;
- live VRAM/BAT ownership for the now source-guarded glyph transfer path;
- live MPR/bank certification for the exploration movement candidate module;
- scene/mission coverage proving which text and movement variants are reused;
- evidence that any proposed injection storage is owned for the full lifetime
  of the hook.

No global escape marker is permitted. The failed Stage 1 experiments already
showed that apparent marker absence inside extracted dialogue does not imply
runtime-global safety.
