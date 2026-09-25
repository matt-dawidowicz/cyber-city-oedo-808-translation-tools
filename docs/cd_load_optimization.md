# CD load-time optimization

Status: reverse engineering active; no release-speed mutation enabled yet.

## Executive finding

The long transitions are real CD work, not an intentional software pause.

The common movement module contains two source-guarded scene loaders:

- `$423B-$4261`: local RAM/sector loader;
- `$4262-$428D`: VRAM byte loader.

Both prepare a System Card `CD_READ` request, call `$E009`, and immediately
retry on a nonzero status. Neither contains a VSync wait, frame countdown, or
deliberate delay that can simply be removed.

The first optimization target is therefore **less seeking and less data
movement**, not deleting a wait loop.

## Full dialogue-transition latency

The earlier hot-bundle measurement of roughly 1.5 seconds covered the spacing
between three scene CD_READ starts.  It did **not** represent the complete
player-visible transition.

The historical Mission 0 trace contains a second, more important repeated
pattern: five reads used to enter portrait/dialogue presentation. Four captured
instances measure from the first CD request to the first parser execution at:

- 370 frames = 6.17 s;
- 372 frames = 6.20 s;
- 342 frames = 5.70 s;
- 344 frames = 5.73 s.

Each transition moves only ten source sectors total, a pure 1x streaming floor
of about 0.133 s. Therefore roughly 5.6-6.1 seconds per occurrence are outside
the raw streaming floor.

The representative first source sequence is:

```text
$1425 -> $1426 -> $10DD -> $1441 -> $1458
```

with destinations:

```text
$8000, $29D0, $29D0, $9000, VRAM $4000
```

The source-start deltas are:

```text
+1, -841, +868, +23 sectors
```

so the load path oscillates hundreds of sectors backward and forward to fetch a
tiny event/dialogue resource in the middle of otherwise nearby assets.

The first captured request starts at frame 220. Data from its one-sector read
does not begin landing until about frame 286 (~1.10 s). The adjacent $1426
request reaches the next loader call about 11 frames later, while the $10DD
request is followed by a ~151-frame gap before the $1441 read begins. This
strongly implicates seek/command/setup cost rather than transfer bandwidth.

This five-read transition is now the highest-priority layout target.

## Historical Mission 0 trace

The existing 12,510-frame Mesen V5 route contains:

- 36 CD_READ calls;
- 17 load bursts;
- 537,728 transferred bytes;
- 185,408 bytes represented by one copy of each exact read signature;
- 352,320 bytes of additional repeated signatures.

Thus 65.52% of the bytes transferred in that captured route belong to read
signatures that occurred more than once.

This is not proof that 65.52% may be skipped. RAM and VRAM destinations can be
overwritten between reads. It does show that repeated scene/resource
installation dominates the route and gives us concrete cache/relocation
targets.

The largest repeated exact transfer is:

```text
sector $22E8
type   $FE (VRAM bytes)
dest   $0900
length $EE00 = 60,928 bytes
count  5
```

The four complete repetitions after its first occurrence account for 243,712
additional transferred bytes by themselves.

## The hot three-read scene bundle

A particularly expensive bundle appears four times as the same sequence:

| Source | Destination | Amount |
|---|---:|---:|
| `$228E` | RAM `$4000` | 7 sectors / 14,336 bytes |
| `$22DE` | RAM `$9000` | 3 sectors / 6,144 bytes |
| `$22E8` | VRAM `$0900` | 60,928 bytes / 30 source sectors touched |

Observed starts:

- frames 885 -> 920 -> 975;
- frames 5103 -> 5139 -> 5194;
- frames 9207 -> 9242 -> 9297;
- frames 11730 -> 11765 -> 11820.

The first-to-third call span is consistently about 90 frames, or 1.5 seconds at
60 Hz.

The source starts are not contiguous:

```text
$228E -> $22DE = +80 sectors
$22DE -> $22E8 = +10 sectors
```

That makes this bundle the first seek-layout target.

## Transfer floor

At the PC Engine CD's 1x 75-sector/s data rate, the complete raw bundle touches
approximately 40 sectors of source data:

```text
7 + 3 + ceil($EE00 / $800) = 40 sectors
40 / 75 = 0.533 s
```

The observed ~1.5-second call span is substantially above that pure streaming
floor. The gap is consistent with command/seek/setup cost in addition to raw
transfer.

Do not interpret 0.533 seconds as a prediction of achievable runtime. Exact
entry-to-return timing is being added to the new Mesen profiler.

## Contiguous bundle strategy

The first mutation prototype should duplicate/relocate the three components
into one **owned contiguous CD extent** and update only the proven scene
descriptor/caller references.

The goal is:

```text
new_A: 7 local sectors
new_B: 3 local sectors immediately following
new_C: graphics immediately following
```

The game can still issue separate reads to the different RAM/VRAM
destinations, but the optical source positions become sequential instead of
jumping 80 sectors and then 10 more.

This keeps the first prototype small:

- no cache-coherency assumption;
- no new persistent RAM requirement;
- no change to the scene's decoded data;
- no decompressor required.

It directly tests how much of the pause is seek/layout overhead.

A relocation destination must be proven/created by the build system. Existing
zero/08/E5-filled sectors are not considered owned merely because they look
empty.

## Compression candidate

After the contiguous-layout benchmark, the next candidate is a small
word-oriented PackBits decoder.

Why PackBits first:

- decoder is small;
- no large dictionary is needed;
- output length is deterministic;
- 16-bit words map naturally to VDC writes;
- malformed streams are easy to source-guard/reject;
- it gives a realistic HuC6280 baseline before considering a more complex LZ
  decoder.

Authenticated payload measurements:

| Asset | Raw | 16-bit PackBits | Ratio | Sector saving |
|---|---:|---:|---:|---:|
| `$22E8` large VRAM | 60,928 | 29,458 | 48.3% | 30 -> 15 (15) |
| `$25C2` large VRAM | 60,928 | 34,294 | 56.3% | 30 -> 17 (13) |
| `$1458` portrait/UI | 8,224 | 5,870 | 71.4% | 5 -> 3 (2) |
| `$1561` portrait/UI | 8,224 | 3,742 | 45.5% | 5 -> 2 (3) |

For the hot bundle, compressing only `$22E8` changes the pure transfer floor
from 40 sectors to 25:

```text
7 + 3 + 15 = 25 sectors
40 / 75 = 0.533 s
25 / 75 = 0.333 s
```

That is about 0.20 seconds of raw-transfer saving by itself. The larger
opportunity is **compression plus contiguous placement**, because the observed
pause includes much more than the raw 1x transfer floor.

Desktop zlib compresses the correctly addressed `$22E8` asset to 15,455
bytes and `$25C2` to 17,774 bytes.
Those figures are useful upper-bound comparisons only; zlib is not a proposed
runtime dependency.

## 8 KiB bank $87

Historical multi-interaction capture observed heavy activity in physical
CD-RAM bank `$85` but zero R/W/X activity in bank `$87` during that window.

A prior controlled V6 probe was written specifically to test bank `$87`
residency across bartender/menu/exit/re-entry behavior. The probe's code exists,
but its final operator log is not currently in the repository.

Therefore bank `$87` is a **candidate**, not yet release-owned storage.

If its lifecycle gate closes, 8 KiB is enough for:

- a decompression input ring buffer;
- small portrait caches;
- decoder tables/workspace;
- sequential compressed streaming.

It is not large enough to retain the uncompressed 60,928-byte scene graphic.

## New measurement path

Use:

```text
cyber-oedo analyze-cd-loads cyber_oedo_cd_load_profile.log
cyber-oedo analyze-cd-transitions cyber_oedo_translation_capture_v5.log
cyber-oedo analyze-cd-hot-assets track02_mode1_2048.bin
```

For new captures use:

```text
tools/mesen_cd_transition_profiler_v2.lua
```

The v2 profiler dynamically registers each observed BIOS return target and
therefore measures every `CD_READ` from entry to the exact caller return. It
also times the generic byte loader and marks the first dialogue parser
execution after a long idle interval.

The profiler records:

- every System Card CD_READ;
- source LBA;
- destination;
- byte/sector mode;
- current scene/room selectors;
- MPR map;
- generic byte-loader calls;
- physical bank-$87 activity;
- exact entry-to-return latency for the source-guarded scene loaders at
  `$423B` and `$4262`.

## Optimization order

1. **Measure exact read duration.** Establish entry-to-return frame cost for the
   hot bundle instead of inferring from call spacing.
2. **Contiguous-source prototype.** Relocate/duplicate the hot bundle into one
   owned extent without compression and benchmark the same route.
3. **Word-PackBits prototype.** Compress the large VRAM block and stream/decode
   it through a proven staging bank.
4. **Cache small resources.** If bank `$87` residency is certified, retain
   high-frequency small assets whose compressed forms fit.
5. **Generalize by scene descriptor.** Generate optimized bundles for other
   repeatedly visited rooms only after the first prototype has measured wins.
6. **Do not optimize voice waits.** Dialogue opcode `21` waits for real ADPCM
   voice completion and is part of presentation semantics, not scene-load
   overhead.

## Release gates

A load optimization is not promoted until all of these pass:

- source hashes and exact loader guards;
- unchanged decoded RAM/VRAM result;
- scene entry/exit/re-entry;
- interaction/menu behavior;
- audio and ADPCM behavior;
- save/load;
- MPR/bank-lifetime monitoring;
- exact before/after Mesen frame measurements;
- no new writes/execution in storage classified as cache/workspace;
- full raw Mode 1 EDC/ECC rebuild for every modified sector.
