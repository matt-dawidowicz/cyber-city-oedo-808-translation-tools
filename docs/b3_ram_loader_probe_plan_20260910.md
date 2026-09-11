# B3 RAM / loader probe plan

Status date: 2026-09-10  
Branch: `b3/self-contained-renderer-space-proof-20260910`  
Purpose: identify deliberate runtime residency for the English renderer/font

## Why this is now the critical path

The production text design no longer needs to minimize font bytes at the cost of
quality. The first complete 103-glyph 8x16 1-bpp font is only 1,648 bytes, and
three complete logical font roles total 4,944 bytes on disc. The remaining
problem is **live residency**, not media capacity.

The glyph-provider boundary is also narrow: stock Mission 0 contains
`JSR $E060` at `$56C0`, `EX_GETFNT` fills `$4C6C-$4C8B`, and execution resumes
at `$56C3`. A custom provider can therefore remain small if it has an owned
place to live and can read a resident font.

## Hardware bank map relevant to the investigation

Public PC Engine memory maps agree on these 8 KiB physical-bank ranges for the
CD/Super System Card environment:

| Physical banks | Size | Hardware role |
|---|---:|---|
| `$80-$87` | 64 KiB | CD-ROM work RAM |
| `$68-$7F` | 192 KiB | Super System Card / Super CD-ROM2 work RAM |

Sources:

- https://github-wiki-see.page/m/pce-devel/huc/wiki/Memory-Map
- https://github.com/mamedev/mame/blob/master/src/mame/nec/pce.cpp

These are **hardware availability facts, not allocation facts**. A bank that
exists as RAM can still be used by the game, System Card routines, ADPCM/CD
transfer code, menus, overlays, save/load logic, or transient scratch state.

## Relation to the live H_BARTEN snapshot

The captured parser stop reported:

```text
MPR0=$FF MPR1=$F8 MPR2=$80 MPR3=$81
MPR4=$82 MPR5=$83 MPR6=$84 MPR7=$00
```

Thus five consecutive CD-RAM banks are mapped into logical pages 2-6 during the
opening bartender path:

| MPR | Logical window | Physical bank |
|---:|---:|---:|
| 2 | `$4000-$5FFF` | `$80` |
| 3 | `$6000-$7FFF` | `$81` |
| 4 | `$8000-$9FFF` | `$82` |
| 5 | `$A000-$BFFF` | `$83` |
| 6 | `$C000-$DFFF` | `$84` |

The remaining base CD-RAM banks `$85-$87` and all Super System Card banks
`$68-$7F` therefore become **probe candidates only**. They must not be called
free until their full scene/module lifetime is demonstrated.

## Candidate priority

### Priority 1: `$85-$87`

These three banks provide 24 KiB immediately adjacent to the live `$80-$84`
Mission 0 mapping. One proven 8 KiB bank would already be ample for an initial
1,648-byte dialogue font plus a small glyph provider and lookup tables.

Questions to answer:

1. Does Mission 0 ever map `$85`, `$86`, or `$87` into an MPR during the full
   bartender scene, menu/redraw paths, ADPCM activity, or scene transition?
2. Does any System Card operation read/write these physical banks without a
   persistent MPR mapping visible at the parser stop?
3. Are the banks used as CD/ADPCM staging buffers or later overlays?
4. Can the existing game CD-read wrapper deliberately load a small asset into
   one of these banks after temporarily mapping it to a logical page?

### Priority 2: `$68-$7F`

These 24 banks provide 192 KiB of System Card v3 work RAM and are attractive for
a larger long-term English subsystem. They are also more likely to have System
Card conventions that must be respected, so availability must be proven rather
than assumed.

Questions to answer:

1. Which of these banks does the game/System Card map during ordinary Mission 0
   play?
2. Are any ranges reserved by BIOS conventions or runtime services used by this
   game?
3. Can one bank be dedicated to a resident font/renderer without disrupting CD,
   ADPCM, backup-memory, or overlay operations?
4. Is a Super System Card bank preferable to base CD RAM for persistence across
   resource loads?

## Mesen capture plan

Run the stock game with the same Japanese System Card 3.0 used for the proven
H_BARTEN trace. Do not patch the renderer during this probe.

### A. MPR lifecycle log

Capture all eight MPR values at these anchors:

- Mission 0 entry;
- immediately before/after the loader routine at `$64CB`;
- CD-read wrapper `$6EBE/$6F50` and BIOS `$E009`;
- parser `$9543`;
- cell renderer `$5915`;
- font call `$56C0` and continuation `$56C3`;
- menu open/close;
- full dialogue-window redraw;
- voice/ADPCM activity;
- end of bartender conversation; and
- transition out of the room/scene.

Any mapping of candidate banks `$85-$87` or `$68-$7F` must be logged with PC,
call stack, and access purpose.

### B. Physical RAM activity

If Mesen exposes physical-bank read/write breakpoints or memory-event logging,
watch candidate banks directly. If it exposes only logical watches, temporarily
map/inspect candidates only in a controlled debugger context and do not leave
MPRs modified while the game runs.

For each candidate bank, the desired evidence is not merely "all zeros". Record:

- initial hash/content summary;
- every observed read/write/execute event;
- MPR mapping interval(s);
- whether contents survive dialogue redraw/menu/ADPCM events;
- whether contents survive the scene transition; and
- whether a later loader intentionally replaces them.

### C. Loader experiment after read-only proof

Only after one bank has a clean read-only lifetime trace should we perform a
controlled load experiment. The existing Mission 0 code already demonstrates a
game-side CD transfer path: `$64CB` prepares a transfer and the `$6EBE/$6F50`
path reaches System Card CD_READ `$E009`.

The first mutation should therefore be deliberately boring:

1. map one proven candidate bank into a disposable logical 8 KiB window;
2. use the game's normal CD-read mechanism to load a tiny authenticated test
   pattern from a deliberately allocated disc resource;
3. verify the exact bytes/hash;
4. restore the prior MPR mapping;
5. continue the complete bartender/menu/ADPCM/scene-exit test; and
6. verify that no unrelated state changed.

Only after that succeeds does the bank become eligible for the dialogue font or
renderer.

## Minimum capacity target

The first playable typography proof does **not** need a large allocation:

- dialogue font: 1,648 bytes;
- glyph metrics/character map: expected to be small, exact size TBD;
- renderer/selector code: exact assembled size TBD;
- scratch: preferably reuse/prove the existing `$4C6C-$4CAB` pipeline rather
  than reserve a large new buffer.

A single proven 8 KiB bank is therefore the initial target. More RAM is useful
for later proportional rendering, multiple resident fonts, or relocated text,
but it is not required to prove the architecture.

## Promotion rule

A physical bank may be marked `owned_for_english_runtime` only when both are
true:

1. static loader/reference analysis shows how its lifetime is controlled; and
2. live tracing covers the complete activity window in which the English
   provider/font will be resident.

Hardware existence, an unmapped MPR snapshot, homogeneous bytes, or temporary
non-use is insufficient by itself.

## Explicit exclusions

- `$9F1B-$9FFF` remains forbidden regardless of apparent content.
- Historical `$A300/$A800` padding is not promoted by this plan.
- `H_BARTEN` must not be extended beyond its declared `$0080` extent.
- No global escape marker is reintroduced.
- No modified BIOS/System Card is permitted.
- Load-time optimization remains out of scope; this probe is about correctness
  and ownership only.
