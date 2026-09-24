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

## Outer event/control boundary

Startup uses $371F to choose new-game/resume behavior and then loads one CD
block directly to logical $D800 before jumping there.

This proves that $D800 is an **outer event/control overlay entry point** and is
separate from the dialogue bytecode interpreter.

The startup source is guarded, but the event opcode language is deliberately
not invented from static disc offsets. The loader's CD block address does not
map naively to `Track2 payload offset = sector * 2048`; the mapped $D800 bytes
must be captured at runtime before assigning opcodes.

Use `tools/mesen_whole_game_live_capture.lua` to collect that evidence.

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

The exploration overlay has no direct readers of $3707-$370B. Those final five
bytes are therefore a **handoff tail** for subsequent scene/action code, not
locally decoded movement fields.

The whole-game Mesen capture records all nine bytes at the interaction copy,
transition promotion, and $D800 outer-event entry so later consumers can be
identified without guessing.

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

After this static pass, the largest remaining unknown is the exact opcode/field
language of the outer $D800 event overlay. New emulator captures are required
to dump the actually mapped code safely.

Other remaining work is narrower:

1. identify consumers of the interaction handoff tail $3707-$370B;
2. determine whether preserved object auxiliary fields are used by another
   overlay rather than the exploration core;
3. live-certify representative Missions 1-8 and ENDING;
4. decode individual binary UI/graphics assets only where modification needs
   them.

The save, ADPCM, movement, collision, object runtime layout, scene loader,
camera, sprite, text, and major graphics architecture are otherwise
substantially source-mapped.
