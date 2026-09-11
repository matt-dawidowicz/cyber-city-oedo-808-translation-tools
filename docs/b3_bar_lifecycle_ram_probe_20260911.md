# B3 bar lifecycle RAM / loader proof

Status date: 2026-09-11  
Branch: `b3/self-contained-renderer-space-proof-20260910`  
Machine-readable lifecycle evidence: `docs/evidence/b3_bar_lifecycle_ram_probe_20260911.json`  
Controlled-load smoke evidence: `docs/evidence/b3_bank87_loader_residency_smoke_20260911.json`  
Manual V6 probe: `tools/mesen/b3_bank87_residency_v6.lua`

## Result

The extended Mesen 2.2.1 capture closed the live-nonuse portion of the `$87`
allocation gate for the tested Mission 0 bar lifecycle.

The capture used the stock Japanese System Card 3.0 and read-only Lua
instrumentation. It covered 12,510 frames, 302 parser hits, 287 renderer hits,
36 BIOS `CD_READ` calls, seven generic byte-loader entries, six dialogue groups,
and 17 CD-load bursts.

The authenticated `H_BARTEN` stream at `$C692` appears in dialogue group 1 and
again in dialogue group 5 after intervening room/resource load activity. Longer
dialogue groups also exercised parser control bytes including `$40` and `$2F`,
so the trace includes more than a straight one-line Shift-JIS render path.

## Physical CD-RAM result

Direct physical `pceCdromRam` callbacks produced:

| Bank | Reads | Writes | Executes | Decision |
|---|---:|---:|---:|---|
| `$85` | 212,682 | 80,257 | 231,065 | Used; positive control; disqualified |
| `$87` | 0 | 0 | 0 | No physical use observed across this tested lifecycle |

No MPR mapping of `$87` was observed during the V5 capture. `$85` was repeatedly
mapped and actively used, including as a destination for BIOS CD transfers.
This validates the physical callback instrumentation rather than merely showing
two zero-filled banks.

**Scope:** this is not a claim that `$87` is globally free across the entire
game. It was sufficient to advance `$87` from an unproven candidate to the
candidate for a deliberate Mission 0 English-runtime load/residency experiment.

## Correct CD coordinate model

The V5 Lua logger printed a field named `track2_payload_off` as `sector * 2048`.
That label was incorrect. The System Card `CD_READ` values observed here are
**absolute disc LBAs** because the active System Card base registers were zero.
Track 2 begins at absolute LBA 3,590 (`$0E06`), so the correct conversion is:

```text
track2_relative_sector = absolute_disc_lba - 3590
track2_payload_offset   = track2_relative_sector * 2048
```

This correction reconciles the live loader with the already authenticated disc
layout. In particular, the live H_BARTEN request at absolute LBA `$0010DD`
becomes Track-2-relative sector `$02D7` and payload offset `$0016B800`, exactly
matching the authenticated H_BARTEN payload base.

A representative common-resource request is therefore:

- destination `$8000`;
- **absolute disc LBA** `$001425`;
- Track-2-relative sector `$061F`;
- Track-2 payload offset `$0030F800`;
- byte length `$0F51` (3,921 bytes).

The game loader reads complete 2,048-byte sectors directly to the requested
logical destination, then uses scratch buffer `$29D0` for a final partial sector
when the byte count is not sector-aligned. Thus the higher-level loader accepts
byte-oriented resource sizes; English resources do not need to retain the
Japanese resource's original logical byte length or be multiples of 2,048.

## First controlled `$87` load: passed

The first runtime residency smoke deliberately avoided inventing a new disc
cave. It reused one existing authenticated source sector as an unmistakable test
pattern and did **not** modify the disc or System Card.

Test payload:

- absolute disc LBA `$0010DD`;
- Track-2-relative sector `$02D7`;
- payload offset `$0016B800`;
- length `$0800` (2,048 bytes);
- SHA-256 `054603d9b31b5d1c4bff6cec3d683c151bf88295f2b312684ebfde0bac3f114a`;
- first bytes `48 5F 42 41 52 54 45 4E` (`H_BARTEN`).

The test waited for the normal H_BARTEN `$6EA0` load to finish. At the loader's
final `RTS`, it temporarily used the now-idle `$29D0` loader scratch buffer for a
155-byte trampoline. The trampoline saved CPU/direct-page/System Card argument
state, saved MPR5, mapped MPR5 to physical bank `$87`, and called the game's real
`$6EA0` loader with destination `$A000`, absolute LBA `$0010DD`, and length
`$0800`.

At `$E009`, the stock System Card received a direct one-sector read to `$A000`
while `MPR5=$87`. Exactly 2,048 physical writes reached bank `$87`. The loaded
bank matched the authenticated sector byte-for-byte. The trampoline then
restored `MPR5=$83`, the displaced stock instruction, and the exact post-natural-
load `$29D0` contents.

The headless smoke continued through frame 1,200 with zero payload mismatches,
zero post-injection writes to `$87`, and continuing H_BARTEN dialogue activity.
This proves the **loader and immediate residency mechanism**; it does not yet
prove full lifecycle ownership.

## Renderer result

The live renderer contract remains:

- parser: `$9543`;
- stock cell renderer: `$5915`;
- stock font call: `$56C0: JSR $E060`;
- stock continuation: `$56C3`;
- System Card glyph destination: `$4C6C-$4C8B` (32 bytes).

The V5 capture recorded nonblank `EX_GETFNT` buffers for ordinary Shift-JIS
characters, confirming that a custom provider can target the actual 32-byte
glyph interface rather than the earlier all-zero full-width-space sample.

## Parser implication

The parser explicitly recognizes single-byte values such as `$40`, `$2A`,
`$2F`, `$5C`, `$7E`, `$3D`, and others as commands. Raw ASCII is therefore not a
safe universal on-disc encoding for English text.

The production path should continue to use a resource-/handler-local English
selector and a dedicated one-byte English codepage whose text values cannot be
misinterpreted as the stock command namespace. Translator-facing text remains
normal Unicode/English; this constraint applies only to the packed game-side
encoding.

## Current promotion state and next gate

`$87` has now passed:

1. the extended read-only non-use/positive-control lifecycle probe; and
2. a controlled direct loader/residency smoke using the stock game loader and
   stock Japanese System Card 3.0.

It is still **not** marked `owned_for_english_runtime` until the loaded payload is
kept resident through the full manual V6 coverage sequence:

1. bartender greeting;
2. NPC dialogue with menu/options and at least one selected branch;
3. leave the bar and let the next area finish loading;
4. re-enter the bar and let the interior finish loading; and
5. interact again after re-entry.

During that run V6 must show no post-injection stock writes/executes to physical
bank `$87` and no payload-integrity failures. After that gate passes, `$87` may
be promoted for the first embedded 8x16 English-font/provider experiment at the
`$56C0 -> $56C3` boundary.

Media allocation remains a separate production question. This smoke reused an
existing read-only sector and therefore does not establish where the eventual
English font/resource payload will live on disc. A production allocation must
be deliberate and independently proven; do not infer ownership from zero/padding
bytes.

All prior exclusions remain unchanged: never use `$9F1B-$9FFF`, do not revive
historical `$A300/$A800` padding, do not extend `H_BARTEN` beyond its declared
`$0080` extent, and do not reintroduce global in-band escape markers.
