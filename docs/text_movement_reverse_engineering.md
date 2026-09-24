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
6. Facing direction.
7. Animation state, frame index, and timer.
8. Collision query and collision response.
9. Walkability/tile or geometry source.
10. Interaction target/range checks.
11. Camera/scroll coordinates and clamping.
12. Door/room/map transition trigger.
13. Entity table layout and stride for NPCs/actors.
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
