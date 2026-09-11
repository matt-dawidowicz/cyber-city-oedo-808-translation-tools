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
| `$9F1B-$9FFF` | **runtime-used System Card interaction range; forbidden injection space** |

`$9F1B-$9FFF` is no longer merely an unowned historical zero region. During a
2026-09-10 Mesen session, a read/write/execute watch on this range fired on a
live read from System Card code near `$F4FC`, with the observed instruction
`LDA ($FA) [$9F1B] = $00`. The call stack passed through System Card code and
the surrounding behavior appears ADPCM-transfer-related. Whatever the exact
subsystem label, the allocation conclusion is definitive: **game-side injected
code or data must never occupy `$9F1B-$9FFF`.** The dated observation is
recorded in `docs/evidence/h_barten_live_runtime_20260910.json`.

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

## B3 H_BARTEN live renderer proof (2026-09-10)

The opening bartender path now has a direct live observation from the ordinary,
stock-renderer route. This is a stronger runtime anchor than the earlier static
allocation assumptions.

The visible same-size replacement identifies `H_BARTEN` as the live opening
resource. Its directory entry declares source sector `0x0110DD` and size
`0x0080`; the resource maps to payload `0x0016B800`, with the dialogue marker
at CPU `$C690` / payload `0x0016B840` and the text body at CPU `$C692` / payload
`0x0016B842`.

At a live stop on `$9543`, Mesen reported:

```text
MPR0=$FF MPR1=$F8 MPR2=$80 MPR3=$81
MPR4=$82 MPR5=$83 MPR6=$84 MPR7=$00
```

Direct-page bytes `$207F/$2080 = 92 C6` therefore resolve the active stream
pointer to `$C692`; because that address lies in the MPR6 window, the stream is
mapped through physical bank `$84`.

The same ordinary path reaches `$5915`, then stock System Card `EX_GETFNT` at
`$E060`. Captured arguments for fullwidth `Ｂ` were:

```text
$F8/$F9 = 61 82   ; Shift-JIS $8261
$FA/$FB = 6C 4C   ; bitmap destination $4C6C
$FF      = 00      ; 16x16 font mode
```

The 32-byte range `$4C6C-$4C8B` was observed empty before `EX_GETFNT` and
contained the generated glyph bitmap after return. Control then returns to game
code at approximately `$56C3`, after which the game continues its own bitmap
processing/rendering path.

These observations support a new preferred direction: retain the stock System
Card and use `EX_GETFNT` only as a **source** for Latin bitmaps, then perform a
small game-side crop/normalize/composite step before resuming the existing game
pipeline. This can potentially eliminate the old 1,520-byte embedded font
asset. It does not yet justify a patch: the adapter still needs proven-owned
executable storage and a record-/handler-local one-byte selector.

The B3 evidence and allocation audit are documented in:

- `docs/evidence/h_barten_live_runtime_20260910.json`
- `docs/evidence/mission0_one_byte_capacity_20260910.json`
- `docs/b3_self_contained_renderer_investigation_20260910.md`

## Runtime proof command

Run:

```text
cyber-oedo prove-dialogue-runtime track02_mode1_2048.bin \
  --dialogue dialogue.tsv --output tier_b_runtime.json
```

The command checks the authenticated Track 2 SHA-256, validates every B1/B2
static code window byte-for-byte, authenticates the Mission 0 indexed-table
source, reports the historical zero region without promoting its ownership, and
correlates `3D` operand pairs from a Tier-A dialogue TSV. Its historical static
label for `$9F1B-$9FFF` must not be interpreted as an allocation candidate; the
2026-09-10 live evidence supersedes that status and marks the range forbidden.

## Gates before Tier-B mutation

The 2026-09-10 trace closes the representative Mission 0 MPR/stream-pointer gate
and establishes the stock `$5915 -> $E060 -> $4C6C -> ~$56C3` glyph path. The
remaining gates before a one-byte English mutation are now narrower:

- prove an executable/storage range owned for the full lifetime of the adapter;
- bound the exact game routine around the `$56C0` font call and its post-call
  `$56xx/$4Exx` bitmap-processing path;
- capture several known Latin glyph bitmaps before and after that processing to
  derive a stable 16x16-to-8x16 transform;
- trace any adjacent `$4C8C-$4CAB` scratch/derived buffer before treating it as
  writable state;
- prove a record-/handler-local one-byte selector whose lifetime survives the
  stock full-window redraw behavior; and
- retain the existing `$A400` state/table proof for dynamic indexed fields as
  Mission 0 translation expands beyond the bartender vertical slice.

No global escape marker is permitted. No modified BIOS/System Card is permitted
as a release requirement. No code or RAM region becomes allocatable from
zero-fill alone, and `$9F1B-$9FFF` is explicitly prohibited.
