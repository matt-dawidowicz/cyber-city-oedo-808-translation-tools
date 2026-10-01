# Fast-load architecture

Status: reverse engineering / prototype design. No speed mutation is release-enabled.

## Live bartender benchmark — MesenCE 2.2.1

A fresh automated replay was run against the authenticated original disc under
MesenCE 2.2.1 + Super System Card 3.0, loading the retained
`cyber_city_oedo_bartender_probe.mss` state and injecting controller input
through Mesen's `inputPolled` callback.

### Exploration -> bartender dialogue

The cold interaction measured:

| event | local frame | elapsed |
|---|---:|---:|
| Button I injected | 60 | 0 |
| CD_FADE mode $0C | 61 | +0.017 s |
| bar 30-VSync loop begins | 92 | +0.533 s |
| bar 30-VSync loop ends | 122 | +1.033 s |
| $1425 dialogue loader begins | 147 | +1.450 s |
| first dialogue parser execution | 517 | +7.617 s |

The measured loader-to-parser window is **370 frames / 6.167 s**.

Blocking operations inside that window:

| operation | frames | seconds |
|---|---:|---:|
| CD_READ $1425, 1 sector -> $8000 | 67 | 1.117 |
| CD_READ $1426, 1 sector -> $29D0 | 10 | 0.167 |
| cold-only CD_READ $10DD, 1 sector | 27 | 0.450 |
| AD_TRANS $1292, 4 blocks | 26 | 0.433 |
| CD_READ $1441, 2 sectors -> $9000 | 24 | 0.400 |
| AD_TRANS $1443, 4 blocks -> ADPCM $E000 | 13 | 0.217 |
| CD_READ $1458, $2020 bytes -> VRAM $4000 | 96 | 1.600 |

Those calls account for **263 frames / 4.383 s**. The same run recorded
**71 explicit EX_VSYNC calls** during the loader window; 64 consecutive calls
come from the routine returning to $7B80 and consume about **1.067 s** by
themselves. Direct transfer time plus explicit VSync gating therefore explains
334/370 frames; only about **36 frames / 0.600 s** remain for other CPU/setup
work.

The bar runtime overlay is not the same copy as the movement overlay containing
the $40DB 120-frame loop. The live bar code performs CD_FADE mode $0C at $421C,
then later executes a **30-frame** EX_VSYNC loop at $4213-$421A. Therefore the
120-frame wait must not be generalized to every exploration -> dialogue
transition.

### Resident module and speaker-local cache benchmarks

Two independent warm-entry cache experiments have now been replayed against the
bartender route.

**Resident dialogue module.** The existing `$8000/$8003` JMP-entrypoint check
was made functional so a resident module branches around the `$1425/$1426`
reload. Both module reads disappear. The first parser hit moves from frame 517
to frame 479, a **38-frame / 0.633-second** improvement. On the second
interaction the self-modified operand bytes `$8617/$8618` begin as `$08/$96`;
the reload is still skipped, the parser is reached correctly, and normal module
initialization rewrites them to `$F0/$04`. The warm path improves by roughly
**34 frames / 0.567 seconds** versus stock.

The saving is smaller than the removed 77-frame module-read duration because
the following optical request inherits part of the seek cost that the module
read previously absorbed. This confirms that deleting one read does not imply
an equal end-to-end saving.

**Speaker-local retention.** NOPing the shipping command-0/command-5 invalidation
of selector `$8FDE` allows the existing two-sector `$1441` speaker-local cache
to survive the selective bar return. The first interaction still reads `$1441`;
the second does not. Warm loader-to-parser time improves from **342 frames /
5.700 seconds** to **330 frames / 5.500 seconds**, a **12-frame / 0.200-second**
saving.

These results are independently valid. A combined resident-module +
speaker-retention harness still needs a bank-correct way to install the
speaker-invalidation patch into the already-resident module in the retained
save state; the first combined Lua attempt modified the wrong backing memory
and therefore is not used as timing evidence.
### Live portrait + ADPCM Card-RAM cache benchmark

A MesenCE 2.2.1 bartender replay now validates the two largest remaining
recurring entry-side cache candidates against the stock parser-ready state.

| configuration | I press -> parser | saving vs stock |
|---|---:|---:|
| stock | 457 f / 7.617 s | — |
| portrait cached in Card RAM | 362 f / 6.033 s | **95 f / 1.583 s** |
| portrait + both observed ADPCM blocks cached | 336 f / 5.600 s | **121 f / 2.017 s** |

The portrait cache uses banks `$68/$69` and a HuC6280 `TIA` RAM-to-VDC copy
with temporary MPR mappings. At parser-ready, the complete 64 KiB VRAM image
is byte-for-byte identical to stock (SHA-256
`c336c787fd110c930eeb2584c9b166b93d03e9fdbd5a5e93abc30822283411b6`).

The ADPCM layer caches the two observed 8 KiB sources separately:

- `$1292` -> Card RAM `$6A` -> ADPCM `$0000`;
- `$1443` -> Card RAM `$6B` -> ADPCM `$E000`.

Each block is mapped at logical `$A000` and written with the existing System
Card `AD_WRITE $E039` local-memory path. Adding ADPCM caching on top of the
portrait cache saves another **26 frames / 0.433 s**. The complete 64 KiB
ADPCM RAM image at parser-ready is also byte-for-byte identical to stock
(SHA-256 `ca7f25e8912c6ea8e7a950c608910c9082a76bdb7c6057b4e655d288169df31b`).

This proves the copy mechanisms and state equivalence in the Mesen benchmark
environment. It does **not** yet provide a permanent preload lifecycle or
release-safe game-code patch; Card-RAM ownership, preload timing, and broader
portrait/voice coverage remain release gates.
### Warm bartender interaction

After returning to the bar, the identical interaction was triggered again.
The warm loader ran from frame 1617 to 1959: **342 frames / 5.700 s**.

The cold-only $10DD H_BARTEN resource read disappeared. The recurring module,
speaker-local, ADPCM, and portrait operations remained. The 28-frame difference
between the cold 6.167 s and warm 5.700 s measurements is essentially the
removed $10DD read. Existing event-resource caching therefore works, but it
does not attack the dominant recurring costs.

### Dialogue -> bar restore

On leaving the dialogue:

| event / operation | measured time |
|---|---:|
| CD_FADE mode $0E to fade-state clear | 127 frames / 2.117 s |
| synchronous $41EC fade-wait subset | 82 frames / 1.367 s |
| CD_READ $228E, 7 sectors | 35 frames / 0.583 s |
| CD_READ $22DE, 3 sectors | 25 frames / 0.417 s |
| CD_READ $22E8, $EE00 bytes -> VRAM | **551 frames / 9.183 s** |

From the mode-$0E fade request to completion of the core scene restore is
**793 frames / 13.217 s**.

The $22E8 operation is the dominant single cost. Mesen's SCSI trace shows it
issues only a 30-sector optical read with a modeled 365 ms seek, but the BIOS
call remains blocked for 9.183 s. Instrumenting VDC I/O during this one call
recorded **66,442 VDC-register writes**: 2,206 register-select writes, 32,118
data-low writes, and 32,118 data-high writes. It contains zero EX_VSYNC calls.

Thus the nine-second cost is primarily a CPU/System-Card-driven transfer into
VDC/VRAM, not optical seek latency. This substantially strengthens the case for
selective dialogue-damage restoration or a RAM/VRAM fast path instead of
reloading the full $EE00-byte exploration image.

### Live VRAM dirty diff and two-span restore

A deterministic no-dialogue control from the same bartender save state changed
**zero** VRAM bytes over the same 835-frame interval. The dialogue replay changed
33,163 of 65,536 VRAM bytes before the stock restore, so the changes are
conversation/transition-induced rather than ambient room animation.

The stock `$22E8` call uses destination word `$0900`, i.e. VRAM byte `$1200`,
and writes `$EE00` bytes through the end of VRAM. Of the 33,163 dirty bytes,
938 are below `$1200` and are intentionally not repaired by this stock call.
The stock call repairs the remaining **32,225 dirty bytes** while blindly
rewriting **60,928 bytes**.

Sector-level diffing shows eight of the 30 source sectors are completely
untouched. The live dirty set inside the stock restore region is covered by two
compact source/destination spans:

| source | VRAM bytes | transfer length |
|---|---|---:|
| `$22E8...` | `$1200-$A01F` | `$8E20` / 36,384 bytes |
| `$2301...` | `$DA00-$F3FF` | `$1A00` / 6,656 bytes |

A runtime prototype reused the game's own `$4459` generic VRAM loader and the
real System Card CD_READ path for those two spans. It did not use instant Lua
VRAM writes for the measured transfer.

| restore | frames | seconds |
|---|---:|---:|
| stock `$EE00` transfer | 551 | 9.183 |
| selective span 1 | 333 | 5.550 |
| selective span 2 | 79 | 1.317 |
| selective total | **412** | **6.867** |
| saving | **139** | **2.317** |

The two-span candidate transfers 43,040 bytes, skipping 17,888 bytes / 29.36%
of the stock transfer. More importantly, the resulting complete 64 KiB VRAM
image is **byte-for-byte identical** to the stock image immediately after the
`$22E8` restore, and the bar renders correctly after return.

This proves a conservative selective restore is viable. It is still benchmark
code rather than a release patch: the next implementation step is to encode the
second loader call in the game overlay and then validate other rooms/dialogue
types, because their dirty spans may differ from the bartender/bar case.

That implementation step is now complete as a source-guarded benchmark mutation.
The patched disc itself redirects the stock bar restore through a small trampoline,
shortens the original descriptor to `$8E20`, and issues the second `$2301/$1A00`
transfer through the stock `$4459` loader. A clean MesenCE replay with **no Lua
memory mutation** reproduced the same 333 + 79 frame timings, returned to the bar
normally, and produced a complete post-restore VRAM SHA-256 of
`c360d332d1afd276078960d4acc78f6ce681ad74df2e7b80bb1de6ea0fbae566`,
identical to stock. The remaining release gates are broader room/dialogue coverage
and ownership certification for the currently zero-filled trampoline area.

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

The authenticated movement overlay proves two different control-flow paths.

On exploration entry, $4003 calls $40E9 for scene/room setup. On exploration
exit, $402B calls $40B1, and $40B1 immediately calls $40DB, which performs
CD_FADE mode $0C plus the fixed 120-frame EX_VSYNC loop. The exit path later
returns from the exploration module at $403C.

Therefore $40E9 is not a phase between the exit wait and dialogue loading;
its adjacency after $40DB-$40E8 in memory was misleading.

The blocking CD_READ helpers live at `$423B-$4261` (local memory) and
`$4262-$428D` (VRAM). Their code is address-adjacent to the guarded
`$40E9-$423A` setup region, but they are **nested callees**, not a later
sequential phase. Existing profiling observes loader returns while scene setup
is still pending.

Therefore three conclusions are safe:

- the exploration exit path directly executes the 120-frame wait;
- $40E9 is an entry/setup routine rather than the next exit-to-dialogue phase;
- the CD_READ wrappers contain no explicit EX_VSYNC delay.

The remaining uncertainty is the handoff after the exploration module returns:
static code alone does not prove that the same interaction immediately reaches
the Mission 0 $1425 dialogue loader.

But setup time and loader time must not be double-counted as separate serial
phases. The maintained diagnostic is:

    cyber-oedo analyze-scene-transition <track2-payload>

No speed mutation is enabled by this analyzer.

### A4. Direction-specific transition state model

The two visible transition directions have different fixed gates and must not
be collapsed into one additive latency budget.

For exploration -> dialogue, the authenticated $402B -> $40B1 -> $40DB
120-frame wait belongs to a different movement-overlay copy. The live bartender
bar overlay instead uses a measured 30-frame wait. These timings must remain
overlay-specific and the 120-frame wait must not be added to the bartender's
5.7-6.2-second loader measurement.

For dialogue -> exploration, command 2 requests the approximately 2.5-second
mode-$0E ADPCM fade and the outer `$41EC` state gate waits for completion.
That fade belongs to the opposite direction and must not be added to the
exploration -> dialogue critical path.

The maintained diagnostic is:

    cyber-oedo describe-transition-state-machine

The v2 Mesen transition profiler now carries a dedicated ordering proof. It
arms on the exploration transition path at `$402B`, then records the
`$40DB` wait, the exploration module return at `$403C`, the `$1425`
dialogue byte-loader invocation, and `$9543` (first parser execution). A
single `ORDER_PROOF_RESULT` line reports whether the exact observed order was:

    $402B -> $40DB -> $403C RTS -> $1425 loader -> $9543 parser

It also reports visible frames from transition exit to parser, wait-to-loader
frames, and loader-to-parser frames. Results from that movement-overlay path
must be interpreted separately from the live bartender/bar benchmark.

This model is descriptive only; all fast paths remain release-disabled.

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

The complete raw bar working set is 110,656 bytes, so **14 banks is the
byte-capacity lower bound**, not necessarily the best executable layout.

A stricter cache planner now models the game's proven 8 KiB local-memory
AD_WRITE source window. Seven active ADPCM source blocks are exactly 8 KiB
each and are therefore most useful when each occupies one whole Card-RAM bank.
The 0x0F51-byte module plus all eight 4 KiB speaker-local blocks then require
five more banks. This gives a **12-bank AD_WRITE-friendly core**.

Adding two 0x2020-byte portraits requires:

- three more banks when RAM-to-VRAM copying may split at bank boundaries:
  **15 banks total**, nine banks / 73,728 bytes left;
- four more banks when each portrait receives an independent two-bank
  allocation: **16 banks total**, eight banks / 65,536 bytes left.

The old 14-bank figure remains useful as a pure capacity floor, but obtaining
that density would require scattering portrait bytes into the small slack
regions left by the execution-friendly core layout. That is not the preferred
first implementation.

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

A further static constraint is now explicit: the raw contiguous disc extent
$1425-$1452 is not itself the ideal in-RAM representation. Several 8 KiB
ADPCM blocks begin two sectors into an 8 KiB bank when that extent is copied
verbatim. Those blocks would straddle Card-RAM banks. For direct reuse of the
existing one-window $A000 AD_WRITE path, the cache should therefore be
**repacked by logical resource**, not treated as a byte-for-byte mirror of the
disc extent. The contiguous disc layout is still valuable for preload seek
locality; the in-RAM execution layout is a separate problem.

### C2. Module versus speaker-local lifetime risk

The two residency experiments should not be treated as equally strong.

The dialogue module occupies logical $8000-$8F50. The known main exploration
scene-local reloads target $4000-$77FF and $9000-$A7FF, so **none of the known
scene-local writes overlaps the module body in logical CPU address space**.

The speaker-local cache is different: the 3-sector exploration load beginning
at logical $9000 covers $9000-$A7FF and therefore completely covers the
dialogue speaker-local window $9000-$9FFF.

This still does not prove physical clobber. HuC6280 MPR mappings may differ
between the dialogue and exploration overlays, so equal logical addresses do
not imply equal CD-RAM banks. But it changes the static risk assessment:

- resident-module reuse has no known logical scene-write conflict;
- speaker-local reuse has a complete logical overlap and therefore requires
  especially strong MPR/physical-RAM lifetime proof.

The benchmarks remain independent for exactly this reason.

### C3. Same-room re-entry state

The source-guarded scene-entry routine exposes a useful asymmetry for dialogue
returns. `$3702` already acts as a position-preservation policy: when it is
nonzero, the routine does not reload player X/Y at `$2760-$2763`.

Other room-entry state is reinstalled unconditionally by that routine:

- room feature byte -> `$264C`;
- object-source pointer -> `$277E/$277F`;
- interaction-table pointer -> `$2779/$277A`;
- two room-loader parameter pairs -> zero page `$1E/$1F` and
  `$421E/$421F`.

Separately, the guarded object initializer rebuilds 16-byte live object state
from compact scene records, and the occupancy-rectangle subsystem has an
explicit count-reset/populate path. This means a future dialogue->same-room
fast return must decide whether live object/occupancy/camera state is meant to
survive rather than simply skipping the stock setup wholesale.

The maintained diagnostic is:

    cyber-oedo analyze-same-room-reentry <track2-payload>

Static evidence does not yet prove which of those initialization routines are
actually entered on every dialogue return. That remains a live phase-boundary
gate, but the state that would be destroyed or preserved is now mapped.

### C4. Physical MPR geometry of the speaker-cache risk

The logical overlap can be narrowed further without assuming a runtime MPR
value. HuC6280 logical `$8000-$9FFF` is one MPR4 window. In the proven dialogue
layout, MPR4 maps physical page `$85`:

- module: page-$85 offsets `0x0000-0x0F50`;
- BSS: offsets `0x0F51-0x0FFF`;
- speaker-local block: offsets `0x1000-0x1FFF`.

The exploration 3-sector load to `$9000-$A7FF` splits exactly at the MPR
boundary:

- `$9000-$9FFF`: 4 KiB through MPR4, page offsets `0x1000-0x1FFF`;
- `$A000-$A7FF`: 2 KiB through MPR5, page offsets `0x0000-0x07FF`.

Therefore:

- if exploration MPR4 is still `$85`, the first 4 KiB overwrites exactly the
  speaker-local half while leaving the module body intact;
- if exploration MPR4 is another page, physical page `$85` survives.

This is stronger than a generic "logical overlap" warning, but it still does
not select which case occurs. The missing proof is specifically MPR4 at the
`$22DE` load (or an equivalent physical CD-RAM checksum).

### C5. Static MPR and same-room call-reference diagnostics

Two additional diagnostics narrow the remaining runtime gates without treating
raw byte matches as instruction-boundary proof.

`analyze-resource-lifetime --payload <track2-payload>` now linearly decodes
the authenticated scene/room setup and scene-loader code regions and reports
only decoded `TAM`/`TMA` operations that touch MPR4 or MPR5. An exploration
MPR4 value is called statically resolved only if every decoded MPR4 write in
those guarded regions is an immediately adjacent, identical `LDA #imm; TAM`
sequence. Otherwise the report deliberately leaves physical bank identity
unresolved and retains the live-MPR/checksum gate.

`analyze-same-room-reentry <track2-payload>` now also decodes direct
`JSR`/`JMP` references from the authenticated scene-orchestration region to
the known entry-selection, object-initialization, collision-registry, and
camera routines. This distinguishes a routine merely existing in the overlay
from scene orchestration actually containing a direct reference to it. Indirect
or data-driven dispatch remains a separate runtime/static-control-flow question.

These diagnostics do not make the speaker-retention or same-room fast-return
benchmarks release-safe by themselves. They reduce the remaining proof to
specific unresolved mappings/call paths rather than broad architectural
uncertainty.

### D. Independent benchmark matrix

Four source-guarded mutations now exist independently so timing changes can be
attributed instead of bundled together:

1. **resident module only** - wire the game's existing JMP-entrypoint probe to
   the stock loader epilogue on a cache hit;
2. **speaker-local retention only** - preserve $8FDE across command-0/command-5
   teardown so the stock two-sector speaker cache can remain valid;
3. **short exploration wait only** - benchmark reducing the explicit 120-frame
   loop to a selected 1-120 frame value (8 frames is the current conservative
   candidate), while keeping the runtime-order proof gate explicit;
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

### E3. Static selective-VRAM restore ceiling

The renderer now gives a useful bound even before a live dirty-range capture.

The portrait destination is fixed at VRAM words `$4000-$500F`, or 8,224 bytes.
All portrait variants reuse that same address family.

The dialogue text grid has 36 slots. Each slot is allocated at:

    $6D00 + cell_index * $40 words

The guarded VDC writer at `$5772` emits sixteen words per call and the setup
path invokes it twice, so one rendered cell actually writes 32 words / 64
bytes. Across all 36 slots, the sparse glyph-pattern writes therefore total
only 2,304 bytes. Their address envelope is `$6D00-$75DF`.

Thus portrait plus all sparse glyph writes total 10,528 bytes, and even treating
the complete glyph envelope as one contiguous restore keeps portrait+glyph
restoration below roughly 22% of the stock 60,928-byte scene transfer.

The live bartender capture shows why this static figure must not be interpreted
as total transition damage. The actual conversation/transition path dirties
33,163 VRAM bytes, including large regions outside the statically bounded
portrait and glyph writers. BAT/display/setup activity therefore contributes
substantial additional damage.

For the bar case, live profiling has now produced and benchmarked an exact
conservative two-span restore. The static renderer bound remains useful for
attribution, but the **live diff is authoritative for patch planning**.

Run:

    cyber-oedo analyze-static-vram-bound

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