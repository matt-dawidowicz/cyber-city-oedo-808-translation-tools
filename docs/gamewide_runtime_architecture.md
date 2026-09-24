# Game-wide runtime architecture

This document consolidates source-guarded findings across the exploration,
interaction, transition, loading, and dialogue systems. It distinguishes common
engine code from relocated overlay copies and scene-specific data.

## High-level flow

```text
Track 2 resources / scene descriptors
             |
             v
        System Card CD_READ
             |
             v
scene + room descriptor installation
             |
             +--> collision bitmap
             +--> entity source table
             +--> interaction table
             +--> map dimensions / room data
             |
             v
       exploration frame loop
             |
             +--> input normalization
             +--> collision / occupancy
             +--> player coordinate commit
             +--> entity animation/update
             +--> camera clamp + scroll
             +--> tile row/column refill
             +--> interaction selection
             |
             v
 transition payload / command handoff
             |
             v
       script/dialogue overlay
             |
             +--> bytecode controls
             +--> cursor/window state
             +--> dynamic record insertion
             +--> System Card font fetch
             +--> glyph VRAM upload
             +--> BAT update
```

## Player movement -> camera -> tile streaming

The coupling is exact and indirect.

1. $4A9E commits one signed unit step to player X/Y at $2760-$2763.
2. The post-step path reaches $4ADB and then $43F6.
3. The camera target is derived independently for X and Y:
   `clamp(player_axis - 128, 0, map_axis_pixels - 256)`.
4. The desired camera origin is compared with the current origin.
5. $4403/$444B send the signed difference to $5EB2/$5EF0.
6. Pixel-scroll state at $220C/$220D and $2210/$2211 advances one pixel at a
   time.
7. When a low nibble crosses a 16-pixel boundary, the corresponding tile origin
   at $289C-$289F advances and the row/column refill path beginning at $602C is
   invoked.

The player therefore remains centered when possible, while the camera clamps
within 128 pixels of a map edge. VRAM map refill is tile-granular even though
camera scrolling is pixel-granular.

## Interactions and Command Mode

Normalized input code 8 is Button I. The Button-I path sets interaction class
$277B to 1 and scans the 18-byte interaction records through $4B20.

Selection is deterministic:

1. iterate records in table order;
2. stop at class FF;
3. require record class == $277B;
4. load the record's eight bound bytes;
5. require $5186 to find player X/Y inside those bounds;
6. accept the first matching record;
7. copy its nine-byte payload to $3703-$370B and set the exploration exit flag.

There is **no direct read of facing/animation state in this scan**. The manual's
"face another character" description is therefore implemented indirectly by
the shape/placement of interaction regions or other scene data rather than a
facing-code comparison in the Button-I selector.

Class 0 is scanned automatically by the movement/input path before the explicit
Button-I class-1 scan. Button II uses a separate branch.

## Entity runtime model

Room descriptors install an entity-source pointer at $277E/$277F.

Source records:

- 8 bytes each;
- first byte FF terminates the list;
- bytes +2/+3 and +4/+5 become entity X/Y;
- additional source bytes select entity/animation behavior.

Initialization expands each live source record into a 16-byte runtime slot
beginning at $2783. The live count is held at $277D.

The initialization path also:

- creates an 8-byte occupancy rectangle for the entity;
- stores the resulting rectangle index in the runtime state;
- chooses animation state from the entity selector;
- writes the completed live slot.

The per-frame entity loop reloads each 16-byte slot, advances its animation and
state, writes it back, and then feeds sprite construction. This separates the
compact scene-authored entity table from mutable per-frame entity state.

## Collision layers

The exploration engine uses three spatial structures with different jobs:

1. **Terrain collision:** one bit per 16x16 map tile, based at $275E/$275F.
2. **Occupancy rectangles:** counted 8-byte rectangles at $265E, count $265D.
3. **Interaction records:** 18-byte class/bounds/payload entries addressed via
   $2779/$277A.

They should not be treated as one generic collision table.

## Room and scene transitions

Persistent exploration selection state is held at:

- $3700: scene selector;
- $3701: room selector;
- $3702: resume/spawn state.

The scene selector indexes a 9-byte descriptor table. Scene loading uses System
Card CD_READ to install data around $7000. The resulting scene data provides map
dimensions, collision/map pointers, and a room-descriptor pointer table.

The selected room descriptor supplies:

| Offset | Static role |
|---:|---|
| +0..+3 | initial player X/Y when $3702 == 0 |
| +4 | scene/room feature byte installed at $264C |
| +5..+6 | entity-source pointer -> $277E/$277F |
| +7..+8 | interaction-table pointer -> $2779/$277A |
| +9..+10 | descriptor used by a room data/CD load |
| +11..+12 | additional loader source used by the room transfer |

A successful interaction copies nine payload bytes to $3703-$370B. The
transition form is identified by $3703 == FF. When that form is present, the
exploration exit path promotes:

```text
$3704 -> $3700
$3705 -> $3701
$3706 -> $3702
```

and returns to the caller, which can reload/re-enter exploration with the new
scene/room selection.

The exact high-level meaning of every non-FF payload variant remains
scene-dependent and is not generalized here.

## Exploration overlays and common engine identity

Two different reuse strategies coexist.

### High-level exploration wrappers

Ten exact copies of the exploration return/transition wrapper are present at
distinct Track 2 bases. They share the $3700-$3702 scene-selection contract.

### Core movement engine

Long signatures covering the movement dispatcher, coordinate commit, terrain
collision lookup, and animation interpreter each occur exactly once in Track 2.
A shorter joypad-normalization idiom has another unrelated copy elsewhere and is
therefore not used as singleton proof.

The evidence supports a common exploration movement core used underneath
multiple high-level scene/mission wrappers.

## Text overlay identity

Ten renderer-bearing text overlays are present, but they map to **two Mission 0
copies plus Missions 1-8**, not one copy per analysis bank:

```text
MISSION_0_A  00074800
MISSION_0_B  00131800
MISSION_1    00CE4000
MISSION_2    017B3800
MISSION_3    0222C000
MISSION_4    02B1C000
MISSION_5    03356800
MISSION_6    03B34000
MISSION_7    04281800
MISSION_8    04848000
```

The complete 1,750-byte renderer/window interval $5444-$5B19 is byte-identical
across all ten copies. The ENDING bank contains neither this renderer signature
nor the common parser anchor, so ending presentation is a separate text
architecture.

Their dialogue parser entries are relocated:

```text
94A7, 9543, 95AA, 95AE, 9580,
950E, 9581, 9526, 94A8, 94A7
```

but the parsers are relocation-equivalent:

- all non-address bytes in the compared dispatcher body match;
- every absolute target changes by the same relocation delta as the parser;
- every control comparison occurs at the same relative offset.

This establishes one shared dialogue bytecode language across the ten copies.

## Dialogue controls

The common parser recognizes:

| Byte | Proven static behavior |
|---:|---|
| 00 | terminate stream |
| 40 | explicit line advance; scrolling occurs when entering row 3 |
| 2A | consume one digit-like operand; set glyph delay $2827 to operand-$30 |
| 2F | up to 20 vsyncs of delay, shortened by low joypad input bits |
| 5C | wait for controller press, then wait for full release |
| 7E | consume one digit-like operand; set per-cell text attribute $2763 |
| 3D | indexed $A400 dynamic-text insertion |
| 21 | interruptible ADPCM voice barrier: while $37F1 holds an active voice/sample selector, wait for the ADPCM driver to clear it; $222D&3 skips the wait |
| >80 | ordinary two-byte Shift-JIS glyph |
| <=80 other | ignored by this dispatcher |

Logical RAM addresses are overlay-local. In particular, text-overlay $2763 is
the cell attribute used by 7E; it must not be confused with similarly numbered
movement-overlay state.

$37F1 is written by the reusable ADPCM playback driver when a voice starts. Its
completion path polls System Card AD_STAT and clears $37F1 when playback becomes
idle. This ties control 21 directly to voice synchronization rather than a
generic asynchronous flag.

## Cursor, window, and text-grid state

The stock dialogue window is represented as a RAM grid:

- cursor column: $30;
- cursor row: $2F;
- grid base: $26F3;
- geometry: 3 rows x 12 cells;
- cell size: 3 bytes;
- cell layout: two Shift-JIS bytes plus attribute;
- total grid size: 108 bytes.

$58CE clears the column and advances the row. Entering row 3 invokes the scroll
routine and leaves the cursor on row 2.

$5AD6 copies rows 1-2 over rows 0-1 and blanks the final 12 cells with
`81 40 00`. $5B06 performs initial grid blanking/reset.

Ordinary glyph flow uses the known 11-cell width, with selected punctuation
permitted to occupy cell 12.

## Dialogue VRAM/BAT ownership

The shared renderer initialization installs:

- BAT/tilemap base: $7900;
- dialogue glyph-pattern VRAM base: $6D00.

A positioned cell render fetches/transforms the 16x16 font glyph, allocates the
glyph pattern at `$6D00 + cell_index * $40`, streams the pattern to VDC VRAM,
then writes the corresponding BAT cell rooted at $7900.

This ties the previously proven EX_GETFNT -> $4C6C/$4C8C -> VDC stream to exact
dialogue VRAM address families.

## Stock text ingress paths

Within the shared renderer-bearing overlay code, the known stock 16x16 glyph
renderer has three cursor-aware ingress forms:

- generic null-terminated two-byte glyph strings;
- ordinary parser Shift-JIS pairs;
- opcode 3D's selected indexed-record field.

There are also positioned/direct cell-render paths that call the lower-level
glyph renderer without passing through the normal cursor dispatcher, including
full-grid redraw/scroll machinery.

This does **not** claim that every graphic-backed label or every non-dialogue
screen in the entire game has been decoded; it defines the complete known
shared stock dialogue renderer paths.

## Reproducible proof

Run:

```bash
cyber-oedo prove-game-architecture track02_mode1_2048.bin \
  --output game_architecture.json
```

The report source-guards the major movement/loading/text windows, checks the
ten exploration-wrapper and text-overlay copies, validates parser relocation
equivalence, and emits the consolidated architecture relationships above.

## Remaining live certification

Static reverse engineering is now substantially complete for these core paths.
The remaining high-value work is empirical correlation rather than basic
structure discovery:

- capture MPR state in representative rooms/missions;
- bind collision bits and interaction records to named map objects;
- decode scene-specific meanings of the remaining non-transition interaction
  payload forms;
- map sprite frame IDs to graphic assets;
- finish naming the non-text formatting opcodes in the ENDING OEDONET stream;
- deepen caller semantics for individual resource-local UI families;
- live-certify the now-mapped non-dialogue/ending paths in representative bank
  states.
