# P0: source-guarded M0B dialogue-tail combined-cache candidate (2026-10-20)

**Research only; does NOT close #46 or certify audio correctness, RAM ownership, multi-mission behavior, or release readiness.** The supported builder continues to reject `adpcm`, `portrait-adpcm`, and `all-seven`, even with unsafe performance acknowledgment.

## Architecture change

The old historical ADPCM cache and the repaired portrait cache both occupied CPU `$4CFA` / original payload `0x1364FA`, so they could not coexist. The candidate leaves the 103-byte repaired portrait routine at `$4CFA-$4D60` and relocates the *same* historical 95-byte ADPCM routine into **`$8F51-$8FAF`**, immediately after the Mission-0-B dialogue module's 0x0F51-byte body. The source tail `0x310751` is zero in authenticated original media. The module loader's source-guarded length immediate at `0x1360C3` changes from 0x0F51 to 0x0FB0, loading the extra 95 bytes, and the dialogue call at `$80E0` redirects to `JSR $8F51` instead of `JSR $4CFA`.

The hook and code now share the same logical dialogue module bank rather than crossing into the Mission-0-B outer overlay. The injected code ends **45 bytes before `$8FDD`**, the direct-index speaker selector; this is a *structural* separation, not proof that no indirect reads or runtime writes use the tail. Source-zero BSS and historical RAM values are **not free-space certification**.

Local source-authenticated disposable test-disc build applied five guarded patches over four raw sectors: two original portrait patches, ADPCM call, module-tail 95 bytes, and loader length. The original `.ccd/.img/.sub` hashes were rechecked. No disc image, BIOS, copyrighted data, or release build is committed.

## Completed emulator result: genuine two-cache build

MesenCE 2.2.1 `--testRunner`, 26,000-frame cold boot with only ordinary controller input:

1. Natural watcher encounter, **Move** selection, return to street, then second watcher interaction reached.
2. At frames **2647, 15955, 23430**, all three shared audio-hook executions show `$80E0 = 20 51 8F` and mapped `$8F51` beginning `43 20 48 43 40 48 A9 6B` — **3/3 resident**.
3. Both portrait loads (frames **15980** and **23441**) show the repaired `$4CFA` prefix `43 01 48 43 20 48 43 40 48 A9 68 53` — **2/2 resident**.
4. At frame **26000**, counters were shared ADPCM=3, portrait=2, interaction scans=20, all code-residency checks passed, final MPR `FF F8 80 81 82 83 84 00`, and testRunner exited **code 0**. A successful route is not evidence of sample-accurate sound or cross-overlay memory ownership.

## First-transfer ADPCM memory comparison

Mesen's read-only `emu.memType.pceAdpcmRam` at frame **3000**:

- **Intended 8 KiB destination ADPCM RAM `$E000-$FFFF`: identical rolling 257/263 polynomial fingerprints** across original and two-cache candidate, `744B7209-1C266BD3-44-00`.
- The full 64 KiB RAM fingerprints differ. Eight-bank analysis finds original and candidate match in 8 KiB banks **0 and 7**, and differ in banks 1-6.
- A **second cold-boot original-vs-original baseline** also differs in ADPCM RAM banks 1-6, while banks 0 and 7 stay identical. These regions are nondeterministic between nominally identical original runs and must not be used to infer a candidate failure or claim full-memory parity.
- This is a **memory-byte comparison at one checkpoint**, not direct audio playback/waveform parity or later speaker samples.

## Unknowns and blocks

1. **Runtime ownership of `$8F51-$8FAF` is not certified.** Pending read/write/execution tracing on authenticated original throughout dialogue and scenes. BIOS DMA or indirect references may elude direct CPU callbacks; mere unchanged bytes during a route are insufficient.
2. Original-versus-combined screenshot comparison is pending. Original-versus-portrait-only had three expected transient portrait speedup frames before converging.
3. Compare transferred ADPCM destination bytes after first, second, and third interactions and listen/compare decoded audio. The above source memory check covers **only frame 3000**.
4. The other nine mission-specific dialogue modules have distinct on-disc LBAs and loader lengths. This hook is in the M0B module, but module-switching/residency through later scenes and missions 1-8 has **not** been live-validated.
5. The candidate is deliberately exposed **only** via `build_unverified_dialogue_tail_candidate(unsafe_research=True)`; supported build profiles remain quarantined.

## Regression methodology

The new candidate's five patches must not overlap, must use original byte guards, and must require explicit unsafe research invocation. CI structural tests validate those facts but **do not prove the prototype runs safely**.

During experimentation, early long-run Lua scripts contained a syntax error in a dynamic MPR state key; those scripts timed out without executing their checks and **are excluded as regression evidence**. A separate corrected script was compiled against Lua 5.4 and then successfully completed the 26,000-frame emulator route described above. All console/log claims above derive from that completed run.

Issue: https://github.com/matt-dawidowicz/cyber-city-oedo-808-translation-tools/issues/46
