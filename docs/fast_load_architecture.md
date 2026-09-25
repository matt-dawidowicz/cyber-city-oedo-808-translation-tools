# Fast-load architecture

Status: reverse engineering / prototype design. No speed mutation is release-enabled.

## Why the pauses approach ten seconds

The old profiler watched CD_READ only. It therefore missed ADPCM optical
transfers through AD_TRANS and did not time the synchronous audio-fade gate.
Historical Mission 0 captures already measure roughly 5.7-6.2 seconds from
the first dialogue-load CD request to the first execution of the new dialogue
parser. The fade path occurs around the resource-setup boundary, so a
player-visible wait approaching ten seconds is structurally plausible. A new
live capture is required before assigning exact seconds to each component.

## Exact fade gate

The dialogue module loaded from LBA $1425 contains command 2 at logical $80E7.
When $37F0 is active and not already $FF it:

1. writes $FF to $37F0;
2. invokes PSG_FDOUT through the PSG BIOS;
3. calls System Card CD_FADE at $E02D with mode $0E; and
4. returns.

System Card documentation defines CD_FADE mode $0E as an ADPCM fade-out of
approximately 2.5 seconds.

The outer Mission 0 transition at $41B0 dispatches command 2 when $37F0 is
active. Later, if transition flag $420B is set, $41EC busy-waits on $37F0
until the dialogue module's periodic audio-status path clears the state.

This is synchronization with audio teardown, not an accidental delay loop.
The v2 Mesen profiler now watches $80E7, $E02D, $8100, $41EC, and $41F1.

## Hidden optical traffic: AD_TRANS

Dialogue-module command 1 also performs:

    AD_STOP
    wait until AD_STAT is idle
    AD_TRANS four CD blocks -> ADPCM RAM

through System Card entry points $E042, $E045, and $E033. Those four sectors
were absent from the earlier 36-CD_READ report.

The active speaker data are deliberately paired contiguously:

| index | local/UI block | ADPCM block |
|---:|---:|---:|
| 1 | $142F-$1430 | $1431-$1434 |
| 2 | $143B-$143C | $143D-$1440 |
| 3 | $1441-$1442 | $1443-$1446 |
| 4 | $144D-$144E | $144F-$1452 |
| 5 | $1429-$142A | $142B-$142E |
| 6 | $1447-$1448 | $1449-$144C |
| 7 | $1435-$1436 | $1437-$143A |

So AD_TRANS adds another BIOS/CD operation and four sectors but normally does
not add a large physical seek after its matching two-sector local block.

## Existing cache behavior

A cold bartender transition includes the one-sector H_BARTEN read around
$10DD. Later cache-hit transitions omit that 10xx read entirely, yet still
take about 5.7 seconds from first CD_READ to parser-ready. Therefore the cold
841-sector detour is a real extra penalty, not the baseline cause.

## Core dialogue/audio extent

The invariant dialogue module plus all active local/ADPCM speaker bundles fit
in one compact source interval:

    $1425-$1452 inclusive
    46 sectors
    94,208 bytes

This is smaller than the additional 192 KiB work RAM available with System
Card 3.0 / Super CD hardware. The original game predates Super CD and the
historical Mission 0 capture never maps the extra $68-$7F bank range. That is
strong evidence for a cache experiment, but not yet a release ownership proof.

## Portrait layout

Mission 0 has 135 consecutive five-sector portrait slots from start LBA $1453
through $16F1. The observed portrait transfer length is $2020 bytes (8,224).
Each five-sector slot therefore contains 2,016 bytes after the observed
transfer length. Across all 135 slots that is 272,160 bytes of untransferred
tail space. These tails are evidence, not automatically writable ownership.

## Acceleration plan

### A. Measure the complete budget

Run tools/mesen_cd_transition_profiler_v2.lua. It now measures every CD_READ
and AD_TRANS entry-to-return, AD_STOP/AD_STAT/CD_FADE activity, EX_VSYNC calls,
the generic byte loader, the fade command and synchronous fade wait, and the
first parser execution after loading.

### A2. Attribute one transition without double-counting

The v2 Mesen profiler now opens a `TRANSITION_BUDGET` window at the Mission 0
`$1425` dialogue byte-loader entry and closes it at the first dialogue parser
execution. Within that same window it accumulates entry-to-return frames for:

- `CD_READ`;
- local-mode `CD_EXEC` where the execute target is runtime-proven;
- `AD_TRANS`;
- `AD_READ`;
- `AD_WRITE`; and
- the synchronous `$41EC` fade wait.

It also reports EX_VSYNC call count and a residual frame budget. The residual is
deliberately not labelled "CPU time": it contains portrait/UI installation,
initialization/display work, uninstrumented waits, and ordinary CPU-side setup.
The analyzer in `cyber_oedo/runtime/transition_budget.py` validates that the
reported serial components sum consistently before converting them to seconds
and percentages.

This avoids the earlier accounting error of summing nested byte-loader and
CD_READ timings as if they were independent costs.

### A3. Static scene-transition call structure

The authenticated movement overlay separates the explicit wait gate from the
scene orchestration entry:

    $40DB-$40E8  exploration audio transition
                  CD_FADE mode $0C + fixed 120-frame EX_VSYNC loop

    $40E9...      scene/room orchestration
                  descriptor selection, runtime setup, and resource-loader calls

The blocking CD_READ helpers live at `$423B-$4261` (local memory) and
`$4262-$428D` (VRAM). Their code is address-adjacent to the guarded
`$40E9-$423A` setup region, but they are **nested callees**, not a later
sequential phase. Existing profiling observes loader returns while scene setup
is still pending.

Therefore two conclusions are safe:

- the 120-frame wait ends before scene orchestration begins;
- the CD_READ wrappers contain no explicit EX_VSYNC delay.

But setup time and loader time must not be double-counted as separate serial
phases. The maintained diagnostic is:

    cyber-oedo analyze-scene-transition <track2-payload>

No speed mutation is enabled by this analyzer.

### A3. Static scene-transition call structure

The authenticated movement overlay separates the explicit wait gate from the
scene orchestration entry:

    $40DB-$40E8  exploration audio transition
                  CD_FADE mode $0C + fixed 120-frame EX_VSYNC loop

    $40E9...      scene/room orchestration
                  descriptor selection, runtime setup, and resource-loader calls

The blocking CD_READ helpers live at `$423B-$4261` (local memory) and
`$4262-$428D` (VRAM). Their code is address-adjacent to the guarded
`$40E9-$423A` setup region, but they are **nested callees**, not a later
sequential phase. Existing profiling observes loader returns while scene setup
is still pending.

Therefore two conclusions are safe:

- the 120-frame wait ends before scene orchestration begins;
- the CD_READ wrappers contain no explicit EX_VSYNC delay.

But setup time and loader time must not be double-counted as separate serial
phases. The maintained diagnostic is:

    cyber-oedo analyze-scene-transition <track2-payload>

No speed mutation is enabled by this analyzer.

### B. Short transition teardown

If live timing confirms the fade is critical-path time, prototype a
transition-specific fast shutdown using existing game/BIOS cleanup paths.
Do not simply NOP $41EC: that wait protects audio state.

### C. System Card 3.0 core cache

For an accelerated English release that explicitly requires System Card 3.0,
test the additional 192 KiB RAM as a read-through cache.

    core dialogue/audio $1425-$1452   94,208 bytes
    bartender portrait                 8,224 bytes
    Mama portrait                      8,224 bytes
    ----------------------------------------------
    bar working set                  110,656 bytes

After one preload, repeated interactions could replace module and speaker CD
reads with RAM copies and cache selected portraits for RAM-to-VRAM copies.

The complete bar working set is 110,656 bytes, which occupies 14 packed 8 KiB
banks and leaves ten Card RAM banks (81,920 bytes) available.

The previous working note misidentified BIOS entry $E03F as AD_WRITE. The
System Card jump table actually places AD_WRITE at $E039 and AD_CPLAY at
$E03F.

The follow-up reverse engineering closes most of that uncertainty. Mission 0
already contains a native 8 KiB ADPCM snapshot/restore path:

- temporarily map physical CD-RAM bank $86 at logical $A000;
- AD_READ an 8 KiB window from ADPCM $E000 into CPU $A000;
- later call AD_WRITE $E039 with CX=$E000, BX=$A000, AX=$2000, DH=$00;
- restore the caller's MPR5.

The historical V5 MPR trace independently records the short MPR5=$86 mappings
predicted by this code.

Therefore an accelerated Super Card cache does **not** need a new low-level
ADPCM writer. The clean experiment is to map a cached $68-$7F Card-RAM bank at
logical $A000 and reuse AD_WRITE's local-memory mode. If live profiling shows
the BIOS preserves/uses the caller's mapping as expected, this removes the
extra ordinary-CD-RAM staging copy entirely. If it does not, bank $87 remains
a candidate 8 KiB staging bank, subject to its separate lifetime gate.

### D. Independent benchmark matrix

Four source-guarded mutations now exist independently so timing changes can be
attributed instead of bundled together:

1. **resident module only** - wire the game's existing JMP-entrypoint probe to
   the stock loader epilogue on a cache hit;
2. **speaker-local retention only** - preserve $8FDE across command-0/command-5
   teardown so the stock two-sector speaker cache can remain valid;
3. **short exploration wait only** - reduce the explicit 120-frame loop to a
   selected 1-120 frame value (8 frames is the current conservative benchmark);
4. **combined fast-load stack** - resident module + retained speaker cache +
   8-frame exploration wait + the separate immediate-audio-teardown benchmark.

All remain benchmark-only. The resident-module path still requires live proof
that the two self-modified operand bytes at $8617/$8618 are in a valid state
when an optical reload is skipped.

### E. ADPCM snapshot timing

The transition profiler now times AD_READ $E036 and AD_WRITE $E039
entry-to-return in addition to AD_TRANS. This closes another hole in the
earlier timing budget: the stock module moves an entire 8 KiB ADPCM window to
bank $86 and back without using CD_READ.

### E2. Main-scene source topology

The main exploration restore uses three source extents:

- `$228E-$2294`: 7 sectors;
- `$22DE-$22E0`: 3 sectors;
- `$22E8-$2305`: 30 sectors touched by the 60,928-byte VRAM read.

So the complete source span is 120 sectors but only 40 sectors are transferred.
The actual unused gaps between loaded extents are **73 sectors** and **7
sectors**. The older 80/10 figures are start-to-start deltas, not literal
unread gaps.

This means one contiguous duplicate/relocation could preserve the same 40
sectors of payload while eliminating 80 skipped sectors of source span. It does
not by itself prove a specific seek-time saving; that still requires live timing
and an owned destination extent.

### F. Scene graphics

Separately, make the 7-sector, 3-sector, and 60,928-byte exploration scene
components contiguous and benchmark 16-bit PackBits on the large VRAM block.

## What is proven

- historical load-to-parser is about 5.7-6.2 s;
- raw streaming time is only a small fraction of that;
- cache hits remove the 10xx event read but not the baseline pause;
- AD_TRANS adds hidden optical traffic;
- a 2.5-second-class fade API is present on the transition path;
- the complete core source set fits in System Card 3.0 extra RAM.

The realistic target is therefore much larger than a few tenths of a second.
If live timing confirms the static model, short teardown plus RAM caching can
remove several seconds from repeated interactions.

## Release gates

No acceleration reaches the normal English build until exact before/after
timing, MPR/cache lifetime, RAM/VRAM/ADPCM equivalence, audio state, scene
re-entry, save/load, mission transitions, EDC/ECC, clean boot, and sustained
playtest all pass.