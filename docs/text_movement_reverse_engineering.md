# Text and movement runtime reverse-engineering campaign

## Objective

Move the project from isolated Mission 0 runtime proofs toward a game-wide,
evidence-backed model of the two systems that most directly constrain a complete
English release and faithful behavioral understanding:

1. text: script dispatch, text sources, dynamic substitutions, layout,
   glyph/font lookup, VDC transfer, window/page state, and resource lifetime;
2. movement: controller sampling, actor selection, coordinates, facing,
   animation, collision, interaction range, camera/map state, and room/scene
   transitions.

The target is not merely to attach names to changing bytes. A subsystem is
considered reverse-engineered when its inputs, state, update routines, outputs,
bank/overlay context, and relevant lifetime/ownership are reproducibly linked.

## Evidence standard

Every runtime claim should carry enough context to distinguish reused logical
addresses:

- PC or breakpoint location when relevant;
- all eight HuC6280 MPR values;
- a 64 KiB logical-memory capture or a bounded source-guarded code window;
- source/media identity for any disc-derived bytes;
- before/after state when assigning write semantics;
- counterexamples where a candidate variable changes for unrelated reasons.

A memory byte changing while Right is held is only a candidate coordinate or
movement flag. The semantic claim requires proving the writer and showing that
controlled changes produce the expected behavioral effect.

## Text workstream

### Already established

- marker-based dialogue records and typed/opaque controls;
- Mission 0 interpreter entry and stream pointer helpers;
- outer-script opcode 2F state mutation for the indexed record table;
- opcode 3D dynamic text insertion and record selection;
- 24 x 32-byte A400 record table loaded from disc;
- stock glyph-cell renderer at 5915;
- confirmed 11-cell ordinary width and punctuation exception behavior;
- System Card font-service involvement;
- bank-aware frozen snapshot validation for the Mission 0 3D path.

### Newly source-guarded static renderer proof

The Mission 0 stock renderer is now traced beyond the cell dispatcher:

- glyph bytes in $02/$03 are passed to System Card EX_GETFNT at $56C0;
- the requested 16x16 font data is staged at $4C6C;
- $4E86 transforms sixteen two-byte rows into a second staging area at $4C8C;
- $570C selects VDC MAWR/VWR and feeds both staging views through $5772;
- $5772 writes sixteen word pairs through VDC data ports $0002/$0003;
- $4A38 computes the BAT/tilemap address and writes the resulting cell entry;
- $5915 remains the 11/12-cell dispatcher and advances the cell column; and
- $59B7 ties per-glyph pacing to $2827 and the low joypad bits at $2228.

Run `cyber-oedo prove-text-renderer-runtime` against the authenticated Track 2
payload to validate the exact code windows.

### Remaining proof targets

1. Live-correlate the proven VDC writes with the exact VRAM/BAT ownership.
2. Record cursor X/Y state before and after ordinary glyphs and controls.
4. Prove 40, 2F, 21, and 5C in multiple live contexts, including repeated
   controls and input-skipped cases.
5. Determine the runtime meaning of 37F1.
6. Establish whether later missions reuse byte-identical interpreter/renderer
   code or load variants into the same logical addresses.
7. Enumerate every non-dialogue text path: fixed records, information screens,
   dossiers, dynamic names, menus, graphics-backed labels, and ending text.
8. For every text path, record storage owner, pointer/addressing scheme,
   maximum observed lifetime, and mutation constraints.
9. Only then design compact-English or relocation machinery.

## Movement workstream

Movement now has a source-guarded static core, but still needs live bank and
scene certification.

The current candidate exploration module at payload base 0x000A4800 contains a
self-consistent CPU-relative movement engine:

- $46F2 reads System Card joy state $2228 and normalizes the first active bit
  into codes 1..8;
- $51E0 stores current/previous input in $276C/$276D;
- $52AA retains only codes 1..4 as current/previous movement directions in
  $276E/$276F;
- the direction tables encode Left=(-1,0), Down=(0,+1), Right=(+1,0),
  Up=(0,-1), plus corresponding 16-pixel projection vectors;
- $2760/$2761 and $2762/$2763 are the 16-bit X/Y pairs consumed and updated by
  the movement code;
- $2767/$2768 hold the signed unit step vector;
- $2769 is loaded with $10 and decremented by the step-commit routine;
- $5409/$490A gate the move before $4A9E commits signed coordinate changes.

This also separates player movement from the older $220C/$2210 observations.
A different source-guarded routine increments those values at sub-tile
resolution and, on 16-pixel boundaries, streams newly exposed map tiles to VRAM
through System Card EX_SETWRT. Those values therefore belong to scrolling/map
rendering machinery and must not be labeled player coordinates without stronger
evidence.

Run `cyber-oedo prove-movement-runtime` against the authenticated payload to
validate the static movement windows. A live MPR capture is still required to
certify that this candidate module is the active exploration overlay in each
scene.

### Collision map

The movement collision path is now statically resolved:

1. $5409 starts from the player's 16-bit X/Y pairs and offsets the footprint by
   X-8 and Y-16.
2. $490A divides both coordinates by 16 to obtain 16x16 tile coordinates and
   applies the signed unit movement vector.
3. $4977 multiplies tile Y by the map width byte at $264A using System Card
   MA_MUL8U ($E0BD), combines it with tile X, divides the linear tile index by
   eight, and adds the collision bitmap base pointer at $275E/$275F.
4. $49CC uses tile-X low bits to select the individual collision bit from that
   byte and returns it in carry.
5. $5409 branches on that carry before movement can reach the commit path.

The static representation is therefore **one collision bit per 16x16 map
tile**. Individual bit meanings and scene-specific bitmap ownership still need
live certification.

### Facing and animation

Facing is represented by the directional animation script selected for the
player rather than by a separate direction byte:

- $2764: animation countdown;
- $2765/$2766: current animation-script pointer;
- walk Left/Down/Right/Up: $4649/$4654/$465F/$466A;
- idle Left/Down/Right/Up: $4675/$467A/$467F/$4684.

$451B interprets scripts as repeated `duration, frame` pairs. Opcode byte FF
is followed by a little-endian pointer and redirects the script, which the
directional sequences use to loop. The moving sequences each contain four
six-tick frames; idle scripts hold one facing frame and loop to themselves.

### Occupancy and interaction records

Two separate structures are now proven and should not be conflated.

**Collision/occupancy rectangles**

- count at $265D;
- base at $265E;
- 8 bytes per entry;
- $4725 writes four two-byte values per entry;
- $47D0 fetches an indexed entry and feeds it to the rectangle-overlap logic.

These are transient physical rectangles used by collision/occupancy checks.

**Interaction records**

The pointer at $2779/$277A addresses an 18-byte record array. $4B9B computes
`index * 18`, proving the stride. Each record is:

| Offset | Bytes | Static role |
|---:|---:|---|
| +0 | 1 | interaction class; FF terminates the table |
| +1 | 8 | four two-byte player-bound values |
| +9 | 9 | matched interaction payload |

$4B20 compares the class against $277B, loads the eight bound bytes, and calls
$5186 to test the player X/Y pairs against them. A hit sets $2649 to FF and
copies the final nine bytes to $3703-$370B.

One transition-form payload is now decoded. When $3703 is FF, the scene loop
promotes $3704-$3706 into $3700-$3702. Those active bytes are then consumed as:

- $3700: scene/resource selector; it selects one 9-byte loader descriptor;
- $3701: scene-entry selector; it selects a pointer to an entry record;
- $3702: position mode; zero reloads player X/Y from that entry record, while
  nonzero preserves the already-established position.

Thus the FF payload form is a room/scene transition header. Other payload forms
and bytes $3707-$370B remain intentionally unnamed until their consumers are
observed.

### Camera coupling

The player/camera relationship is now statically direct. Every coordinate commit
at $4A9E reaches $4ADB, which copies $2760-$2763 into $43F6. That routine
applies the camera dead-zone/clamp and invokes the scroll steppers.

The scroll state is:

- horizontal: $220C/$220D;
- vertical: $2210/$2211.

The steppers move those values at pixel resolution. Whenever the low nibble
crosses a 16-pixel boundary, they update the corresponding map-tile origin and
stream a newly exposed row or column. Player coordinates, camera scroll, and
tile refill are therefore separate but explicitly chained systems.

### Live scene objects and meta-sprites

Scene object definitions are read from the pointer at $277E/$277F as fixed
8-byte source records until source byte 0 is FF. Initialization expands each
object into a 16-byte live record at $2783 + index*16; $277D stores the count.

The source record fields currently proven are:

| Offset | Bytes | Static role |
|---:|---:|---|
| +0 | 1 | animation/type selector |
| +1 | 1 | auxiliary byte, not yet named |
| +2 | 2 | X position |
| +4 | 2 | Y position |
| +6 | 2 | auxiliary word, not yet named |

The live record carries the position plus animation countdown/pointer and the
derived collision-rectangle index. Each frame, the engine copies the 16-byte
record to scratch, advances its animation, then writes the record back.

Animation frame IDs index the meta-sprite table at $5A37. Each frame is:

`component_count, [pattern_word, signed_x, signed_y, attribute_word]...`

Each player frame $14-$27 has two components. The directional mapping is:

- Down walk: $14-$17; idle: $25;
- Left walk: $18-$1B; idle: $24;
- Right walk: $1C-$1F; idle: $26;
- Up walk: $20-$23; idle: $27.

This resolves the player animation all the way from direction script to exact
sprite pattern words and per-component offsets/attributes.

### Controlled capture matrix

| Baseline | Changed state | Main purpose |
|---|---|---|
| idle | Right held | X coordinate / horizontal velocity / facing |
| idle | Left held | signed/directional confirmation |
| idle | Up held | Y coordinate / vertical movement |
| idle | Down held | signed/directional confirmation |
| idle | action button | interaction / action state |
| idle | one animation step | animation timer/frame without movement |
| before wall | push into wall | collision resolution |
| before doorway | cross doorway | map/room transition |
| before camera edge | cross edge | camera/scroll state |
| actor A active | actor B active | actor/entity table stride and selector |

Run each pair through the diff-live-state diagnostic. The first pass should
intersect candidates across opposing inputs:

- Right/Left common writers suggest horizontal movement state;
- Up/Down common writers suggest vertical movement state;
- bytes changing only on collision suggest contact/blocked flags;
- contiguous repeating structures after actor switches suggest entity records;
- MPR changes at doorways or scene transitions identify overlay/resource swaps.

### Required movement proofs

1. Controller/joypad read routine and raw input bit layout.
2. Edge/held/repeat input state, if distinct.
3. Active actor/entity selector.
4. World/screen X and Y representation and precision.
5. Velocity or per-frame delta representation.
6. Live-certify directional animation selection across representative scenes.
7. Live-correlate the now-decoded player meta-sprite pattern words with VRAM
   graphics ownership.
8. Live-certify collision bits and occupancy rectangles in representative rooms.
9. Determine the source/loader lifetime of each scene's collision bitmap.
10. Decode non-transition interaction payload forms and bytes $3707-$370B.
11. Live-certify camera dead-zone/clamp behavior across representative rooms.
12. Live-certify the scene-transition selector/entry/mode triplet.
13. Decode the remaining auxiliary fields in the 8-byte object source record.
14. Overlay/MPR changes associated with movement/map transitions.

## Bank-aware state diff diagnostic

The diff-live-state command compares two complete logical-memory snapshots and
reports:

- exact memory SHA-256 values;
- MPR changes;
- number of changed bytes and contiguous ranges;
- before/after bytes for each changed range;
- physical page:offset notation under both MPR mappings;
- explicit truncation if the report is capped.

This is a candidate generator, not a semantic oracle. Once a small set of
addresses is isolated, the next step is read/write breakpoints and bounded
HuC6280 disassembly around the writers.

## Completion criterion

Almost fully reverse-engineered for these systems means we can draw a
source-backed graph from:

input or script bytes -> dispatch -> state mutation -> renderer or movement
update -> RAM/VRAM or world-position output -> transition/lifetime

for representative scenes in every mission, with variants explicitly called out
rather than silently assumed identical.
