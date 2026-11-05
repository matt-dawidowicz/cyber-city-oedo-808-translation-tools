# P0: rejected transient dialogue-tail ADPCM location (2026-10-20)

**Decision: REJECT CPU `$8F51-$8FAF` as an independently owned executable cave. Leave #46 open and all ADPCM-containing performance profiles quarantined.**

This summarizes a disposable, original-source-authenticated combined ADPCM + portrait cache experiment. The experimental binary and BIOS are NOT in this repository, and no release profile was altered.

## Why it looked promising

The historical speaker ADPCM routine (95 bytes) and repaired portrait cache (103 bytes) previously collided at CPU `$4CFA`, source Track-2 offset `0x1364FA`. In the throwaway experiment the portrait routine stayed at `$4CFA`; ADPCM was copied into the on-disc 0xAF-byte tail following M0B dialogue-module LBA `$1425` at CPU `$8F51` / source offset `0x310751`. The module-loader length at `0x1360C3` was source-guardedly increased `0x0F51 -> 0x0FB0`; the module-local `$80E0` JSR redirected to `$8F51`. All five total patches were source-guarded and physically nonoverlapping.

The real 26,000-frame MesenCE 2.2.1 watcher -> **Move** -> street -> second watcher replay completed **with exit 0**, 3/3 expected ADPCM hook/cave entries (frames 2647, 15955, 23430), 2/2 portrait loader/cave entries (15980, 23441), 20 interaction scan callbacks and restored MPRs `FF F8 80 81 82 83 84 00`.

A separate screenshot replay exited successfully. Of 16 captured candidate checkpoints, 15 had a previously recorded authenticated original counterpart. **12/15 pairs were byte-identical**; frames **23400, 23500, 23600** differed during the expected second portrait-loading acceleration (864, 13803 and 4432 differing RGB pixels respectively). All comparable checkpoints from **23700 to 26000** were byte-identical.

At frame 3000, `emu.memType.pceAdpcmRam` shows identical original-versus-combined fingerprints in the **intended 8192-byte target `$E000-$FFFF`**: `744B7209-1C266BD3-44-00`. Other ADPCM memory regions were nondeterministic even across repeated **original-versus-original** cold boots; comparing all 64 KiB is therefore not a valid invariant without initialization control. A matching first-transfer memory fingerprint is **not** proof of audio playback fidelity.

## Decisive negative ownership result

Despite the call-entry success, the new routine did **not** remain resident between uses: at frame 2700, when MPR4 again mapped the same dialogue bank, `$8F51` began `A8 34 A9 A9 85 10 A9 34`, not the injected code prefix `43 20 48 43 40 48 A9 6B`. The candidate routine was visible again on the later audio calls, then overwritten again during transition. Even an exact first- and second-NPC screenshot comparison cannot establish independent ownership.

The authenticated **original-game** (unpatched) 26,000-frame-targeted read/write/exec range probe found direct CPU accesses to the proposed `$8F51-$8FAF` span:

| Original-game checkpoint | Reads | Writes | Execution callbacks |
|---|---:|---:|---:|
| Frame 3000 | 0 | 0 | 0 |
| Frame 6000 | 95 | 0 | 0 |
| Frame 15955 | 281 | 95 | 528 |
| Frame 16500 | 524 | 95 | 1230 |
| Frame 23430 | 673 | 190 | 1386 |
| Frame 24000 | **916** | **190** | **2088** |

**Important:** this original-only probe exceeded its execution limit after reaching frame 24000; it did not certify frame 26000. It nevertheless gives decisive evidence of live **reads, writes AND executions** by stock code. CPU callbacks also do not exhaustively prove hardware DMA ownership. Source-zero tails do not mean spare executable memory.

The earlier shared-module `$90D4` candidate was independently found populated with live data. The pre-`$4CFA` portrait cavity was overwritten in normal play. The repaired portrait cave `$4CFA-$4D60` is already reserved. None of these sites is a verified safe second executable destination.

## Repository safeguards

`cyber_oedo/runtime/adpcm_code_cave_ownership.py` now records the exact known-rejected Mission-0-B CPU windows and has a **fail-closed** assessment: being absent from the known-rejected list never produces runtime/release certification. `tests/test_adpcm_code_cave_ownership.py` asserts that known collision sites and this live dialogue tail are rejected, and that original ADPCM-containing builder profiles remain disabled.

The discarded code-generating prototype was isolated in [research PR #51](https://github.com/matt-dawidowicz/cyber-city-oedo-808-translation-tools/pull/51). **It must not be merged or enabled.** Early long-run Lua diagnostics had a quoting syntax error; their timeouts were not game regressions. All positive claims above came from separately syntax-checked, successfully completed testRunner runs; the negative original-region probe is explicitly partial.

## Next viable architecture and release gates

Build a genuinely independent **private executable bank** with explicit authenticated source loading and *live lifetime/ownership proof*. Its call trampoline must remain valid at every possible `$80E0` invocation, map and restore the correct MPRs, and have a source-safe BIOS `AD_TRANS` fallback if the bank is not resident. Do not use a volatile dialogue BSS tail as the trampoline or code store. Test real ADPCM destination bytes **after each call**, decoded audio playback, module/overlay transitions, and missions 0 through 8 before considering any optimization enabled.

Keep [P0 issue #46](https://github.com/matt-dawidowicz/cyber-city-oedo-808-translation-tools/issues/46) open until a proven architecture and cross-mission test suite exists.
