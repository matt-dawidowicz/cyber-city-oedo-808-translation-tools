# October 16-17, 2026 — Live exact-pixel proportional English in Mesen

## User-approved scope and verdict

**DONE, narrowly:** a newly built 8×16 authored Latin font is laid out at
**variable pixel widths before tiling**, decoded from an extra authenticated
CD extent into Super System Card RAM, and displayed through the game's native
Mission-0 text window under MesenCE 2.2.1. The intro diagnostic then returns
to the Japanese source and the game continues. A combined seven-edit cache
experiment runs through the same controlled intro without the previously
reported invalid-sector loop.

**NOT DONE:** unmodified real bartender conversation/return, full-scene line
pagination, authentic source-script insertion, all other missions, optimized
dialogue timing/input menus/interaction hitboxes, audio equivalence, or
full-game regression. The screenshot still shows a **deliberately displaced
bartender test line during the opening narration**, NOT a translated intro
or a screenshot of the actual bar.

This work is a controlled engineering proof, not a candidate public release.

## What changed

- `cyber_oedo/text/vwf_exact_cells.py` now calls the existing bitmap-line
  renderer **before** dividing the line into 16-pixel staging cells. This
  avoids whole-glyph packing slack and allows glyph strokes to cross the cell
  boundaries without additional spacing.
- `mission0_pool_pilot.py` gains an **opt-in** `--vwf-pilot` flag, requiring
  `--authored-pixel-font`. It inserts the exact staged cell dictionary in
  four originally all-zero Track 2 tail sectors and loads it via the real
  System Card `CD_READ` into physical Card RAM bank `$73`. It retains the
  existing four-bank `$7C-$7F` stream pool and keeps source guards and normal
  MPR / BIOS argument restoration. Default English pilot remains unchanged.
- `engine_polish_pilot.py` can also opt in to `--vwf-pilot` alongside the
  **seven** source-guarded experimental non-feature performance edits. The
  known-broken resident-module shortcut remains excluded.
- `tests/test_vwf_exact_cells.py` reconstructs original 176-pixel full-line
  output from the staged 16-pixel cells bit for bit, tests line controls and
  the three-row bound, verifies the authenticated unused-sector guard, and
  checks that the VWF flag is never silently enabled.

No original game assets, BIOS, patched disc, or user-owned savestates
are committed.

## Reproduce live diagnostic (original source required)

~~~sh
python -m cyber_oedo.runtime.mission0_pool_pilot \
  /path/to/authenticated-original.ccd \
  /tmp/oedo-vwf-intro \
  --authored-pixel-font \
  --vwf-pilot \
  --diagnostic-intro-redirect
~~~

Or combine with the independently gated seven-patch cache experiment:

~~~sh
python -m cyber_oedo.runtime.engine_polish_pilot \
  /path/to/authenticated-original.ccd \
  /tmp/oedo-seven-plus-vwf \
  --english-pilot --vwf-pilot --diagnostic-intro
~~~

With MesenCE 2.2.1 configured with the Japanese Super CD-ROM 3.0 BIOS:

~~~sh
Mesen --testRunner --enableStdout --timeout=150 \
  --pcEngine.port1.type=PceController \
  tools/mesen_vwf_intro_trace.lua \
  "/tmp/oedo-vwf-intro/Cyber City Oedo 808 [M0B External Pool Pilot].cue"
~~~

Use the generated manifest's runtime labels to confirm the trace's exact
hook addresses. Inspect the emulator's SCSI output independently for invalid
disc sectors. Screenshots require opt-in Lua IO and are not part of the
read-only trace tool.

## Recorded emulator evidence

Two independent full-disc test builds: authentic original source, same
Japanese System Card BIOS, same Run and Button-I input sequence,
MesenCE 2.2.1.

| Observation | VWF-only diagnostic | 7-cache-edits + VWF diagnostic |
|---|---:|---:|
| $7B dispatcher during intro | frame **5570** | frame **5575** |
| Extra VWF cell-table CD read | frame **5676** | frame **5681** |
| BIOS CD read sector (disc LBA) | **44655** | **44655** |
| External English pool reads | 4 | 4 |
| Staged line cells rendered | **7** | **7** |
| Return to original source handler | frame **5750** | frame **5755** |
| Invalid-sector retries in captured window | none | none |
| Snapshot, frame 5770 | equal | **byte-identical** |

The frame-5770 screenshot SHA-256 for *both builds* was
`609e9298c37c2d1c97799abf18b9f8540c209ece39c108246a11a5a6179e3204`.
No game-pixel difference was introduced by the seven performance edits
during this **single controlled intro**.

The combined diagnostic image had 19 source-guarded edit regions and 15
changed Mode-1 sectors. The resulting game IMG was **not distributed**.

## Critical limitations

- This is a **live VWF mechanism proof** for one temporary opening diagnostic
  line. It does *not* establish correct line-by-line text reveal timing,
  multipage layout, scroll/redraw preservation, speaker portraits, voice
  barriers, actual menu integration, bar return, missions 1–8 or original
  hardware support.
- The font atlas has a current 95-slot working repertoire; the latest
  Definitive Edition English workbook/TSV was not available for a new
  whole-script coverage audit.
- One 8 KiB Card-RAM cell dictionary is sufficient for this pilot, not
  necessarily thousands of script lines. Production needs per-resource
  font/cell lifetime management and an exact code/data coexistence audit.
- Seven-cache intro adds 5 frames before dispatch in this run. That does
  **not** contradict the separate historical bar benchmark improvements:
  the bar benchmark timings must be repeated for the integrated build.
- Previous combined nine-edit benchmark containing resident-module reuse
  **hung on invalid CD sector 336976** during intro. That shortcut must stay
  off until root cause and safe memory residency are proven.
- Existing instructions explicitly forbid adding a case file, mid-mission
  saves, extra hints, UI interaction prompts, puzzles or new gameplay
  mechanics. Only optimize the established controls and presentation after
  capturing and comparing actual behavior.

## Next live test gates

1. Reach Mission-0 **real** bar using natural controller inputs;
   record a deterministic checkpoint/replay sequence without in-game
   memory edits and compare original vs combined seven-cache+VWF.
2. Capture entry/return full timing; prove returned **RAM, VRAM and ADPCM**
   match stock, with no music/voice state drift.
3. Exercise the actual patched bartender record including any voice,
   multipage controls, branching and return to street.
4. Measure specific existing controller/command delays and audio glitches
   before writing any interaction/menu/fade changes.
5. Extend read-only state/replay coverage over Mission 0 then missions 1–8.

CI passing is a prerequisite. It is **not** proof of these gamewide gates.
