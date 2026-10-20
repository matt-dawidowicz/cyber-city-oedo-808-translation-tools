# P0 watcher Move/return/re-entry: source-authenticated emulator evidence (2026-10-20)

## Correct controller interpretation

The natural watcher does **not** become unresponsive: at CPU `$5B7D`, the authenticated Mission-0-B overlay contains `AD 2D 22 29 53 F0 F9` (read `$222D`, mask actionable keys, loop if zero). Later `TST #$01,$222D` and `TST #$02,$222D` branch on the I and II key edges. The game's `$222C` holds button state, and `$222D` briefly records newly pressed input (one frame in the measured long-held test). Sampling only every 20/200 frames hid those pulses. The earlier claim that the emulator was failing to deliver input would be incorrect.

A visual stock-disc probe identifies **移動 (Move)** in the watcher's command menu. A 10-frame Up press at frame 17600 selects Move; a 10-frame I press at frame 17700 confirms. CPU executes `$5B95` at 17700, leaves the previous `$5B7D` wait, transitions through a black loading screen, and returns to a visible street scene by frame 22500. It does **not** require forcing PC, editing RAM, or a savestate.

## Verified full cold-boot A/B: natural watcher, dialogue exit, return

Using identical standard controller input on authenticated original and portrait-only experimental discs, the 25,500-frame Move/return test captured the same 24 checkpoints. All **24/24 screenshot PNGs are byte-identical** across discs. They include the Move-menu selection, fade/loading transition, and street restoration through frame 25500. Both end with exactly:

```
ADPCM=2 portrait=1 scan=14 menuI=3 menuII=0 loop=1 transition=1
```

These counters are **execution-hook hits**, not independent audio transfers or proof of audio waveform identity.

## Second interaction reached, with a timing difference

A separate input schedule moves the player right at frames 23000-23109 and pulses I after that, reaching the watcher for a **second real interaction**. Both original and portrait-only builds recorded three entries to the shared ADPCM call, two portrait loads and 20 interaction-scan hits. The initial 29,500-frame version continued to pulse I after entry, so from frame 23400 onward 22/44 screenshot checkpoints diverged; the original at 23500 still showed a blank dialogue background while portrait-only had already drawn the portrait. Repeated I caused further text/menu time alignment differences. The final redundant menu-I hit counts were 83 and 84 respectively.

**Do not misreport the second-interaction test as screenshot-identical.** Earlier speedup-induced visual differences are expected from an optimized portrait path, but correctness and text stability require another test with I released immediately after re-entry (currently being evaluated). Do not interpret the overlap with the old ADPCM implementation as fixed.

## Follow-up safety obligations

The historical combined portrait/ADPCM caves overlap at source `0x1364FA`; the ADPCM redirect is in a shared dialogue module and its overlay-independent residency remains unproved. Keep all ADPCM-containing build profiles quarantined and issue #46 open. No performance optimization is release-certified by these tests. Repository tests and CI alone cannot establish complete audio fidelity.

## Controlled second-entry parity: I released after re-entry

The refined read-only schedule holds Right only during frames 23000-23109, pulses I during frames 23110-23499, and supplies **no further input**. A full 26,000-frame cold boot was completed separately for both authenticated original and portrait-only builds.

**Final counts are identical** for both games:

```
ADPCM=3 portrait=2 scan=20 menuI=3 menuII=0 loop=1 transition=1
AD_READ=3468 AD_WRITE=4
MPR=[FF F8 80 81 82 83 84 00]
```

Across the 37 checkpoint screenshots, **34/37 PNG pairs are byte-identical**. Only frames 23400, 23500, and 23600 differ, around the second portrait load. The source at 23500 has not yet drawn the portrait, while the patched portrait path has. **Every recorded screenshot from frame 23700 through 26000 is byte-identical**, with no further button presses. This is strong route-specific visual evidence for restored parity after the portrait-loading speedup and second interaction; it is not proof of audio waveform identity, other scene residency or correctness of the historically overlapping combined ADPCM profile.

The reproducible, fail-closed script is `tools/mesen_p0_watcher_second_interaction.lua`. Run each disc independently, preserve its Lua script-data PNGs after each run, compare source versus patched screenshot names and only treat `P0_SECOND_RESULT success=true` as route-level success. Game assets, emulator and BIOS must be independently user-supplied.
