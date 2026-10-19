# P0: natural NPC ADPCM regression - 2026-10-18

This is a cold-boot, ordinary-controller replay of the **street watcher NPC**, NOT the naturally reached Mission 0-B bartender. It proves one real dialogue encounter and gives us a repeatable baseline for #46, but does not satisfy #45.

Repro: [tools/mesen_p0_natural_npc_regression.lua](../tools/mesen_p0_natural_npc_regression.lua). Run in fresh, separate MesenCE 2.2.1 portable instances for the source disc and an authenticated --english-pilot --vwf-pilot disc with **performance_experiment=none**:

    Mesen --testRunner game.cue mesen_p0_natural_npc_regression.lua --timeout=120 --enableStdout

Use the Japanese Super CD-ROM 3.0 BIOS, validated 88-track CUE, PC Engine controller on port 1, and enable Debug.ScriptWindow.AllowIoOsAccess so screenshots can be written. Keep the original disc, BIOS, generated discs and screenshots OUTSIDE GitHub.

Original track 2 SHA-256: 0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223

## Replayed route

- Until frame 8600: Run taps before 600, then I taps to clear the intro.
- Frames 8600-13299: right.
- Frames 13300-15599: up.
- Frames 15600 onward: right plus intermittent I to interact with the nearby watcher.

No forced PC, arbitrary RAM writes, savestate shortcut, or changed inputs between discs. The script logs all eight MPRs, the actual common module call, the current $4CFA mapping, and screenshots at 6000, 8600, 13300, 15600, 16500, 17000 and 17800.

## Observed stock vs English-VWF A/B

| Check | Original | English/VWF |
| --- | --- | --- |
| Natural street navigation and watcher NPC | reached | reached |
| Shared dialogue ADPCM call $80E0 | 2 total | 2 total |
| Portrait loader $8405 | 1 | 1 |
| Interaction scan $4B20 | 14 | 14 |
| Instruction at $80E0 during natural watcher | 20 33 E0 | 20 33 E0 |
| Existing mapped bytes at $4CFA | 12 zero bytes | 12 zero bytes |
| MPR0-7 at the natural $80E0 call | FF F8 80 81 85 83 84 00 | same |
| Screenshots through frame 17000 | six captures byte-identical | six captures byte-identical |
| Frame 17800 screenshot | 70 pixels differ from pilot | 70 pixels differ from original |

At frames 16500 and 17000 the screenshot SHA-256 is the same for both discs:
2116612962b3c18c9c956b3d8ba7e9750fc436a0bd4863595639837b0f847a8e.

**Limit:** the 70-pixel frame-17800 divergence was NOT explained or waived, and there is no scripted proof of subsequent dialogue completion, second interaction, later missions, or normal bartender. This is an NPC reachability and callsite proof, not full visual/runtime parity.

## Root cause and containment

At frame 15955 of the natural NPC encounter, stock executes the shared dialogue module's $80E0 JSR $E033 with MPR2=$80 and MPR4=$85. The former speaker-cache experiment rewrote this to JSR $4CFA, but $4CFA is a zero-filled location in the then-mapped overlay. Its injected cave exists only in the Mission-0-B outer-overlay source. An apparently successful isolated bar test cannot validate such a cross-overlay call in the rest of the game.

PR #42 now **refuses** the adpcm, portrait-adpcm, and all-seven experimental build profiles, even with the unsafe opt-in. This eliminates the known unsafe global transfer from generated discs but does NOT implement a new production-safe ADPCM cache.

## Remaining P0 release gates

- #45: Reach the actual bar naturally, confirm $7B English pool and VWF dispatch, reads, continuation, portraits/voice, timing, and street/second-interaction return.
- #46: Design a safely resident trampoline or overlay-local cache hook, prove it by natural cold-boot A/B including later scenes, and investigate the 70-pixel discrepancy.
- Do not turn on experimental performance or release certification based on this narrow test.
