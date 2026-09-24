# Whole-game reverse-engineering status

This document records the remaining systems outside the already-mapped text and
movement cores. It distinguishes proven structure from runtime work that still
requires emulator evidence.

Run:

```bash
cyber-oedo prove-whole-game-systems track02_mode1_2048.bin \
  --output whole_game_systems.json
```

## Save data

The game uses one System Card backup-memory file named `OEDO808`.

The payload is exactly four bytes:

```text
slot 0: one progress/mission byte
slot 1: one progress/mission byte
slot 2: one progress/mission byte
slot 3: one progress/mission byte
```

Zero denotes an empty slot. When saving, the current progress selector at
$371F is written to the selected byte; zero is coerced to one. The shared save
wrapper writes exactly four bytes from $268F-$2692. Startup reads the same four
bytes into $2E91-$2E94, selects the requested slot, rejects zero, and copies the
nonzero value into $371F.

The save/read implementation is byte-identical across Missions 1-8 and ENDING.
Startup has a relocated read-side implementation for the same BRAM file.

No explicit game-side checksum is present in these guarded wrappers. Error
handling follows backup-memory API return/status behavior.

## Mission controller / outer event control

Startup uses $371F to choose new-game/resume behavior and loads absolute disc
LBA $106F to logical $D800.

Because Track 2 begins at disc LBA 3590, this block maps to Track 2 relative
sector $0269 and payload offset $00134800. The complete 2 KiB controller is now
source-guarded.

The important architectural correction is that $D800 is **not another bytecode
VM**. It is executable HuC6280 mission-control code.

Its entry saves the X/Y call selectors and uses Y as an indirect dispatcher.
The seven static targets are:

```text
Y=0 -> $D800 / normal entry handling
Y=1 -> $D897
Y=2 -> $D948
Y=3 -> $DA74
Y=4 -> $D800
Y=5 -> $DA4F
Y=6 -> $D940
```

The controller contains three arrays of fixed four-byte CD descriptors. Their
format is:

```text
+0 high LBA byte
+1 low LBA byte
+2 middle LBA byte
+3 CD_READ block count
```

Table A at $D803 has nine records and is used by one alternate Y=1 dispatcher
path when the saved X/Y call selectors differ. Table B at $D827 has nine
records and is the normal progress-indexed mission-module path. Table C at
$D8CA is used by interaction-driven progress transitions.

$371F is multiplied by four to select the appropriate descriptor; the chosen
module is loaded to logical $4000 and the exploration engine is entered.

So persistent progress is directly tied to mission-module selection:

```text
BRAM slot byte
   -> $371F
   -> progress-indexed 4-byte CD descriptor
   -> module load at $4000
   -> exploration / scene control
```

The Mesen capture remains useful for proving which selector paths occur during
real play, but the controller's static architecture no longer depends on a new
runtime dump.

## ADPCM voice architecture

The reusable ADPCM driver uses a six-byte descriptor table beginning at logical
$8BA2:

```text
record = $8BA2 + (sample_id - 1) * 6

+0  CL transfer-address byte
+1  DL transfer-address byte
+2  CH transfer-address byte
+3  AD_TRANS block count
+4  playback length low
+5  playback length high
```

The main voice path uses sample-rate code $0E.

Playback state:

```text
sample selected
   |
   v
descriptor lookup
   |
   v
AD_TRANS / playback setup
   |
   v
sample ID -> $37F1
   |
   v
AD_STAT polling
   |
   v
playback idle -> $37F1 = 0
```

The first 64 six-byte descriptors are source-guarded as a proven table prefix.
This links the previously decoded dialogue `21` command to concrete voice
records rather than an opaque asynchronous flag.

## NPC / live object state

Each scene starts with fixed eight-byte object source records:

| Offset | Static role |
|---:|---|
| +0 | animation/type selector |
| +1 | auxiliary byte |
| +2/+3 | X |
| +4/+5 | Y |
| +6/+7 | auxiliary word |

Initialization expands each source record into a 16-byte live record at
$2783 + index*16:

| Offset | Runtime role |
|---:|---|
| +0/+1 | X |
| +2/+3 | Y |
| +4/+5/+6 | zeroed/reserved in this exploration core |
| +7 | animation countdown |
| +8/+9 | animation script pointer |
| +10 | occupancy-rectangle index |
| +11/+12 | preserved source auxiliary word |
| +13 | animation/type selector |
| +14 | preserved source auxiliary byte |
| +15 | reserved |

The exploration core contains no direct readers of the preserved auxiliary
fields at +11/+12, +14, or +15. They therefore remain intentionally unnamed
rather than receiving speculative NPC semantics.

Per frame, a live record is copied to $2823-$2832, updated/rendered, then copied
back to its 16-byte slot.

## Interaction payloads

Interaction records contain a nine-byte payload copied to $3703-$370B.

The exploration overlay consumes:

- $3703 as the command/type byte;
- `FF` as the proven scene-transition form;
- $3704-$3706 as scene selector, entry selector, and position mode for that
  transition form.

The exploration overlay itself has no direct readers of $3707-$370B, but the
mission controller resolves one important handoff field:

- payload +6 is $3709;
- if $3709 is below $10, the Y=1 controller follows the ordinary return path;
- if $3709 is $10 or greater, it subtracts $10, stores the result in $371F,
  indexes module table C at $D8CA, loads that module to $4000, and returns to
  exploration.

Thus payload +6 is a **progress/module-transition selector**. Payload bytes
+4/+5 and +7/+8 remain unconsumed by both the exploration core and this startup
mission controller and stay intentionally unnamed.

The whole-game Mesen capture records all nine bytes at the interaction copy,
transition promotion, and $D800 controller entry so later mission-specific
consumers can still be correlated without guessing.

## Scene loading

The following scene architecture is already source-guarded by
`prove-game-architecture`:

- scene/resource selector;
- 9-byte scene descriptors;
- scene-entry selector;
- optional player spawn restore;
- collision bitmap pointer;
- object source pointer;
- interaction-table pointer;
- System Card CD_READ argument construction;
- transition promotion from interaction result to the next scene.

The remaining scene work is runtime naming/certification, not discovery of the
basic loader structure.

## Graphics

Already proven:

- PC Engine 4bpp background-tile codec;
- opening title as a 960-tile planar graphic;
- player meta-sprite table and six-byte component format;
- player directional frames and exact pattern words;
- camera pixel scrolling and 16-pixel tile refill;
- common dialogue glyph-pattern VRAM and BAT paths;
- information-page rectangular BAT/tile drawing.

Named UI assets such as `INVENTRY` and `KANSHIKI` remain binary assets whose
ownership/loading is understood but whose internal packed schemas are not
invented. Decode one only if translation or graphic replacement actually
requires modifying it.

## Runtime certification

Load:

```text
tools/mesen_whole_game_live_capture.lua
```

It is read-only and captures:

- $D800 outer event entry;
- exploration loop and transition promotion;
- interaction scan and payload copy;
- object initialization and per-frame updates;
- ADPCM start/completion/descriptor lookup;
- CD_READ;
- BM_FREE/BM_READ/BM_WRITE;
- all eight MPRs;
- $371F progress;
- $3700-$370B scene/interaction state;
- four save bytes;
- active voice state.

Logical addresses are reused heavily. A PC hit without its MPR mapping is not
sufficient runtime evidence.

## Remaining whole-game work

After this static pass, the $D800 controller itself is mapped as executable
dispatcher code rather than an opcode language.

Remaining work is narrower:

1. identify consumers of the still-opaque interaction bytes $3707/$3708 and
   $370A/$370B;
2. determine whether preserved object auxiliary fields are used by another
   overlay rather than the exploration core;
3. live-certify representative Missions 1-8 and ENDING;
4. decode individual binary UI/graphics assets only where modification needs
   them.

The save, ADPCM, movement, collision, object runtime layout, scene loader,
camera, sprite, text, and major graphics architecture are otherwise
substantially source-mapped.
