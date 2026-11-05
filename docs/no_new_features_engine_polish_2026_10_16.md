# Engine polish without new features — controlled Mission 0 test

**Status:** October 16, 2026. Implemented **experimental** test-disc
assembly and an A/B opening replay. **NOT production safe, NOT merged.**

## Editorial/product boundary: improve the existing game, do not add mechanics

Approved polish targets:

1. **Loading and scene return:** reduce avoidable portrait, voice,
   module and scene reload costs while matching stock final RAM/VRAM/ADPCM.
2. **Existing text/UI presentation:** integrate the already-authored
   8x16 variable-width font, better line wrapping, preserve the existing
   per-glyph reveal/advance/cancel semantics and original controls.
3. **Existing interactions:** improve only demonstrated missed-action regions
   or unnecessarily delayed responses, after checking overlap/priority with
   neighbouring actions and NPCs. Do not add target prompts or affordances.
4. **Existing menus:** translate existing commands clearly, preserve command
   order/IDs, reduce measured redundant waits and input lockout.
5. **Existing audio/scene fades:** fix demonstrable discontinuities and
   avoid unnecessary stalls without silencing voice barriers or changing the
   soundtrack/dialogue and music cue ordering.

**Out of scope:** new case-file/journal, hint/navigation overlay, rewind or
history feature, mid-mission or suspend saving, new prompts/icons, new
combat/movement mechanics, puzzle simplification, new story content,
remixed audio, and layout redesign. None are silently introduced.

## Delivered reproducible engine test-disc builder

New command:

~~~sh
python -m cyber_oedo.runtime.engine_polish_pilot \
  /path/to/original.ccd /path/to/new-test-directory
~~~

For an **independent** A/B render check, opt in to the existing English
pilot and its already-proven introductory diagnostic *separately*:

~~~sh
python -m cyber_oedo.runtime.engine_polish_pilot \
  /path/to/original.ccd /path/to/new-test-directory \
  --english-pilot --diagnostic-intro
~~~

The builder authenticates all three original CloneCD companions,
verifies the entire Track 2 SHA-256
`0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`,
checks every expected source byte and byte-range non-overlap, makes a
**new** derived CloneCD/CUE set, rebuilds affected Mode-1 EDC/ECC,
and writes `engine_polish_manifest.json` with sector/byte identities.
Original game and BIOS are not committed or shipped.

The default **7 source-guarded edits** are:

- 2 portrait read-through patch/cave edits (Super System Card RAM);
- 2 ADPCM read-through patch/cave edits (retains stock audio playback);
- 3 selective Mission-0 bar scene-restore patch/cave edits
  (stock CD-to-VDC fallback architecture).

No hard-cut audio command, blind wait-loop NOP, stale speaker-local
retention or global input/interaction mutation is enabled.
On a combined English test the respective cache banks
`$68-$6C` and English pool banks `$7C-$7F` are disjoint.
Disjoint bank labels are **not** a substitute for frame-by-frame
lifetime certification.

## Real emulator regression and isolation: exclude resident-module reuse

The original earlier nine-patch composer included a resident
dialogue-module skip at CPU `$48A6` with cave `$4C6A`. It matched all
authenticated source signatures and passed Python unit tests, but it
FAILED a new clean MesenCE 2.2.1 full-intro replay.

All three runs used the *same* original disc, Japanese Super CD-ROM 3.0
BIOS, controller inputs, English-pilot diagnostic and Mesen settings:

| Variant | Natural diagnostic $7B event | Runtime observation |
|---|---|---|
| English-only pilot | Yes, frame 4,122 | Standard controlled English path |
| Old all-nine-cache-patches + English | No | Black screen and repeated invalid CD sector 336,976 reads |
| Resident-module shortcut only + English | No | Black screen / no redirect by frame 4,600 |
| **All cache edits EXCEPT resident module** + English | Yes, frame 4,127 | No invalid-sector reads through frame 4,600 |

This isolates resident-module reuse as an unsafe dependency for this
opening path. It does **not** prove why the shortcut failed; the
resident check can only be reintroduced after full cold/warm module
initialization and signature/MPR transition tracing. **The new
`engine_polish_pilot` excludes these two edits entirely.**

## Existing measured individual-benchmark evidence

From `docs/fast_load_architecture.md`, **not** from this combined build:

- Stock bartender Button I -> first parser: **457 frames (7.617 s)**.
- An independently cached portrait+ADPCM path: **336 frames (5.600 s)**.
- Stock large VRAM scene restore: **551 frames (9.183 s)**.
- Source-guarded two-span restore: **412 frames (6.867 s)**,
  final VRAM byte-identical to stock in the bar benchmark.

These results must **not** be added or presented as measured benefits
of the seven-edit combined test disc. The current opening smoke only
proves the intro survives that particular input path.

## Gates before ANY polished-game release

1. Repeat cold/new-game, Mission 0 bar, return, second conversation,
   alternate NPCs and room transitions in clean Mesen; compare
   RAM, **all VRAM**, ADPCM data and audio state vs original.
2. Measure input-to-parser and scene-return frames **as one sequence**,
   including CD_READ, AD_TRANS, VDC transfer and fades. Never double-count.
3. Verify pointer/bank lifetime under scene re-entry, audio playback,
   command menus, all original saves/reloads and alternate System Card state.
4. Complete live variable-width font staging, cursor/scroll, pagination,
   deliberate timing and stock Japanese fallback. Simulated screenshots
   are **not** emulator evidence.
5. Capture user-input and interaction rectangles for rooms before
   modifying any hitbox; detect overlapping class-1 rectangles and
   first-match precedence, preserve all exact interaction payloads.
6. Preserve ADPCM voice barriers and all original CD-DA/fade cue order.
   Do not hard-cut audio merely to chase a lower frame count.
7. Full Missions 0–8 + ending, a second accurate emulator, and
   if possible original hardware / optical-drive emulator.

**Source tests passing, disjoint patches and a successful boot are necessary
but do not constitute release certification.** Keep independent opt-in
build layers; never merge experimental code as a finished edition.

## Replay the recorded intro A/B locally (no user-facing feature)

Use `tools/mesen_polish_intro_smoke.lua` with a local MesenCE 2.2.1,
Japanese Super CD-ROM System 3.0 BIOS, generated CUE and:
`--testRunner --enableStdout --pcEngine.port1.type=PceController`.
The script presses Run at frames 90–194, then Button I at 700–734,
and prints status at frames 600, 4200, and 4600. It modifies **no game
memory**, and includes no proprietary ROM/BIOS bytes or screenshots.

For a diagnostic English disc only, expected control evidence is one
`NATIVE_7B` around frame 4122; the seven-patch build gave one around
frame 4127. Inspect the emulator SCSI output separately for **invalid
sector** messages and compare actual screenshots and audio behavior.
Passing this intro test is not sufficient to certify the bar cache
or normal gameplay. The old nine-patch build must not be re-enabled.
