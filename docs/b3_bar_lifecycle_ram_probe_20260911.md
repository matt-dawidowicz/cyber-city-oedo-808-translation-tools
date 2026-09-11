# B3 bar lifecycle RAM / loader proof

Status date: 2026-09-11  
Branch: `b3/self-contained-renderer-space-proof-20260910`  
Machine-readable evidence: `docs/evidence/b3_bar_lifecycle_ram_probe_20260911.json`

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

No MPR mapping of `$87` was observed during the capture. `$85` was repeatedly
mapped and actively used, including as a destination for BIOS CD transfers.
This validates the physical callback instrumentation rather than merely showing
two zero-filled banks.

**Scope:** this is not a claim that `$87` is globally free across the entire
game. It is sufficient to advance `$87` from an unproven candidate to the
candidate for the first deliberate English-runtime load/residency experiment in
the Mission 0 bar lifecycle.

## Loader result

The game's generic byte-oriented resource loader is at `$6EA0`, and its BIOS
sector read path reaches System Card `CD_READ` at `$E009`.

A representative request was:

- destination `$8000`;
- Track-2-relative LBA `$001425`;
- byte length `$0F51` (3,921 bytes).

The loader read one complete 2,048-byte sector directly to `$8000`, then read the
next sector to scratch buffer `$29D0` and copied only the required remainder.
Therefore the higher-level loader already accepts non-sector-aligned byte
lengths. English resources do not need to preserve the Japanese resource's
original byte extent or align their logical size to whole sectors.

This is the key mechanism needed for deliberately relocated English text/font
assets on the data track.

## Renderer result

The live renderer contract is now also well enough bounded for a first custom
provider experiment:

- parser: `$9543`;
- stock cell renderer: `$5915`;
- stock font call: `$56C0: JSR $E060`;
- stock continuation: `$56C3`;
- System Card glyph destination: `$4C6C-$4C8B` (32 bytes).

The V5 capture recorded nonblank `EX_GETFNT` buffers for ordinary Shift-JIS
characters, confirming that a custom provider can be tested against the actual
32-byte glyph interface instead of the earlier all-zero full-width-space sample.

## Parser implication

The parser explicitly recognizes single-byte values such as `$40`, `$2A`,
`$2F`, `$5C`, `$7E`, `$3D`, and others as commands. Raw ASCII is therefore not a
safe universal on-disc encoding for English text.

The production path should continue to use a resource-/handler-local English
selector and a dedicated one-byte English codepage whose text values cannot be
misinterpreted as the stock command namespace. Translator-facing text remains
normal Unicode/English; this constraint applies only to the packed game-side
encoding.

## Promotion and next gate

`$87` is now **eligible for a controlled English-runtime load experiment**.
It is not yet marked `owned_for_english_runtime`.

The next experiment must:

1. allocate an authenticated test/font payload on disc without extending an
   existing resource past its declared extent;
2. use a deliberate loader path to load it into physical bank `$87`;
3. save and restore the affected MPR mapping cleanly;
4. verify the loaded bytes/hash;
5. run the same bartender + menu/control-flow + exit/re-entry lifecycle;
6. verify the English payload remains correct while stock game state remains
   intact; and
7. keep the stock System Card 3.0 unmodified.

Only after that residency experiment succeeds should `$87` be promoted to
`owned_for_english_runtime` and used for the first embedded 8x16 English glyph
provider at the `$56C0 -> $56C3` boundary.

All prior exclusions remain unchanged: never use `$9F1B-$9FFF`, do not revive
historical `$A300/$A800` padding, do not extend `H_BARTEN` from `$0080` to
`$0800`, and do not reintroduce global in-band escape markers.
