# MesenCE 2.2.1 live boot and dialogue smoke test — October 15, 2026

Status: **partial live runtime evidence; the $7B English path has NOT been reached.**
This is not a game-wide English certification or a release gate pass.

## Inputs (not committed to GitHub)

- Authenticated original CloneCD set, with Track 2 Mode-1 payload SHA-256
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.
- Experimental M0-B external-pool pilot built from the PR #42 commit
  `5a7fad948a1d226607cde8369444618514efaa62`.
  Builder manifest lists eight changed Track 2 sector indices:
  `621,623,629,630,631,632,651,41049`.
- MesenCE 2.2.1 Linux x64; Japanese Super CD-ROM System 3.0 BIOS SHA-256
  `e11527b3b96ce112a037138988ca72fd117a6b0779c2480d9e03eaebece3d9ce`.
  The separately provided `syscard3.pce` was verified byte-identical.
- The repository's `python -m cyber_oedo.disc.clonecd_cue original.ccd original.cue`
  produces an 88-track CUE pointing to the *same raw IMG* and does not alter
  proprietary image data. Mesen successfully opened original and pilot CUEs.

## Actual observations

1. With `--testRunner --enableStdout --pcEngine.port1.type=PceController`,
   both original and pilot booted past System Card 3.0 and advanced through
   the animated opening and Japanese narration. Input injection used
   `emu.setInput()` on `emu.eventType.inputPolled`.
2. The opt-in pilot's generated dispatcher exists **in live emulated memory**
   at CPU `$B17A` with the expected `C9 7B` signature. During initial
   Japanese narration, an execution callback recorded **351 dispatcher
   entries**, including A=`$81`, `$89`, `$82` on the first three.
   Original Shift-JIS dialogue displayed normally; no $7B redirect or pool
   load was observed.
3. The on-screen street-like scene after the narration was **not certified as
   the known exploration module**: MPR2 was `$80` and source at CPU `$4000`
   was `20 42 E0`, not the movement module's guarded `20 99 E0` bytes.
   The RAM scene selector was not initialized as documented by the latter.
   Do NOT promote camera movement during this sequence into movement-module
   proof without matching the overlay signature/MPR.
4. A further source-state replay using Mesen `createSavestate/loadSavestate`
   and real controller input activated a **different character conversation**.
   The BIOS execution probe caught `CD_READ` at absolute LBA `$1425`,
   followed by an MPR4 transition into bank `$85`. Mesen displayed the
   character portrait and normal Japanese dialogue. A subsequent
   sample recorded **115 patched dispatches**, zero $7B redirections and
   zero English pool loads. This supports live overlay/dialogue compatibility,
   *not* successful English rendering or a bartender encounter.
5. In this run, the authenticated pilot was not observed executing
   `$B1AD` (pool redirect), `$B26E` (pool loader), or initiating the four
   $7C–$7F Card-RAM requests. The proposed v2 source-skip behavior therefore
   remains synthetic CPU-test-only.

## How to reproduce the smoke test

- Keep CCD, IMG and SUB together. Generate a CUE next to them with the
  existing `clonecd_cue` command, since this Mesen build's CLI does not
  successfully open CloneCD `.ccd` directly.
- Provide the Super CD-ROM System 3.0 BIOS in the Mesen firmware directory.
- When using the headless runner, supply an existing `settings.json`, configure
  `--pcEngine.port1.type=PceController`, and run with `--testRunner`,
  `--enableStdout`, `--testRunnerTimeout=<seconds>`. Send controller
  events via `inputPolled`.
- For initial setup, the boot input used a Run pulse near emulator frame 160;
  Run/I pulses during subsequent interstitial frames advanced to narration.
  The exact schedule is scenario- and state-dependent.
- `emu.createSavestate` is only valid inside an **exec memory callback**,
  not an end-frame callback; state-replay tests need careful MPR/opcode guards.
  Treat an externally restored CPU state as assistance in navigating, not
  a substitute for a continuous natural playthrough.

## Required next proof

1. Navigate to the original M0-B bartender record at payload offset
   `0x00145890` with an unmodified event-control flow.
2. Observe the actual `$7B` instruction in the patched M0-B parser,
   four authenticated CD_READ calls for tail pool sectors, transient MPR3
   bank mapping and restoration, and stock renderer cells containing the
   localized bartender line.
3. Continue through its original script terminator; inspect choices, subsequent
   Japanese text, scene restoration, ADPCM, and save/load.
4. Only then review the last open $7B P1 thread and consider subsequent
   game-wide extension. Keep this pilot `release_enabled=false` meanwhile.

**No user BIOS, ROM, savestate, patched disc, or copyrighted game imagery
is committed to the repository.**
