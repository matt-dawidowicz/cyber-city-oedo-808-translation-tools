# CD-sector / Card RAM ADPCM sidecar (research, 2026-10-20)

**Do not merge as a P0 fix or enable any ADPCM-containing normal build profile.** This branch explores the user's observation that the CD has far more storage than the PC Engine's occupied 8 KiB runtime pages. The unused CD sector is not itself executable: it has to be *loaded into an independently controlled bank and mapped before executing*.

## Source-authenticated layout

The original 88-track CloneCD source is authenticated by its full Track-2 SHA-256 `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`. No copyrighted disc, BIOS or derived game binary is committed.

| Item | Coordinate | Guarded modification |
|---|---|---|
| Original Mission-0-B shared module command body | CPU `$80AF-$80E6`, source payload `0x30F8AF` | Replace exactly 56 stock code bytes (SHA-256 `941661178b27f0054919b55f0853bc0842563c2c0618e1f756f6492cbb45de61`) with 55-byte HuC6280 preloader and one NOP |
| Disc sidecar, separate from dialogue/portraits | Track 2 relative sector `41190`, absolute LBA `$AEEC`, payload offset `0x5073000` | Replace an authenticated **entirely zero** 2048-byte sector with 56-byte relocated stock command plus 95-byte historical ADPCM cache, then zero padding |
| Execution RAM | Super System Card physical bank `$75`, temporarily mapped as MPR3 `$6000-$7FFF` | The original module remains loaded in the known bank at MPR4; no code is placed in the original game's active `$8F51` BSS |
| Portrait-only routine | CPU `$4CFA-$4D60` in M0B outer overlay | Keep previously source-guarded 103-byte portrait cache unchanged |

The small loader temporarily maps bank `$75` into MPR5, sets BIOS `CD_READ $E009` to load exactly one sector into logical `$A000`, restores MPR5, maps bank `$75` at MPR3, calls `$6000`, then restores MPR3. The relocated original 56-byte command retains its relative branches (the local audio-transfer call is redirected from `JSR $E033` to `JSR $6038`), original speaker-table addresses and return behavior. The appended historical 95-byte routine implements the ADPCM read-through. BIOS read failure retries rather than silently omitting audio.

**This adds one extra optical seek/read at every invocation** (not a speedup). Its purpose is to establish correct independent code residence **first**. Future optimization must make the CD helper resident and guarded without relying on unknown ownership or interrupt state.

Four raw Mode-1 sectors changed in the throwaway trial: relative `620, 627, 1567, 41190`. Source EDC/ECC guards were checked before regeneration. Do not add a new CD track or change the directoryless disc's track table; reusing one authenticated unused sector is sufficient.

## Reproduction and observed live evidence

1. Build an isolated image only after full source verification with `build_unverified_cd_sidecar_candidate(payload, acknowledge_unsafe_research=True)`, then apply its source-guarded `PayloadPatch` objects to a private CloneCD IMG copy with rebuilt Mode-1 EDC/ECC.
2. Use MesenCE 2.2.1, Japanese System Card 3.0 and explicit `--pcEngine.port1.type=PceController`. **Without that controller flag**, an apparently clean test may never press Run or reach the natural dialogue; do not call it a code failure.
3. In the first intro call at **frame 2647**, the stock command's source-owned replacement at `$80AF` ran, a physical `CD_READ` requested absolute LBA `$AEEC`, and the relocated original routine plus ADPCM cache both executed in MPR3 bank `$75` at frame **2711**. The patched build kept running through normal introductory progression after the module returned.
4. The first natural watcher call re-entered the bootstrap at **frame 15955**; the relocated original and ADPCM code executed at **frame 16019**, followed by the portrait loader at **frame 16098**. The old `$4CFA` portrait signature remained intact. Dialogue exited via **Move** at frame 17700, and the street was restored.
5. The old exact-frame second-interaction input schedule no longer triggered another watcher by frame 26000 because the extra CD I/O changed timing. This is **not proof of a second-interaction regression or success**. A state-aware/repeating input schedule is under evaluation.

A local Python source verification and **418-unit-test** run passed. This does not certify real audio bytes, uninterrupted IRQ behavior while MPR3 is temporarily changed, bank `$75` ownership in all scenes, second-interaction visual parity, or missions 1–8.

## Hard gates remaining

- Establish a complete second-watcher route with visible and state-correct input, then A/B compare original vs combined screenshots and stable audio-transfer destination RAM after each load. A timing-shifted fixed-input miss must fail.
- Prove `$75` Card RAM bank is owned during each call, no interrupts or BIOS code depend on the original MPR3 during redirected code execution, and module switch/overlay calls cannot invoke an unloaded helper.
- Verify all ADPCM transfer bytes/audio output including errors and retry behavior. One CD read per voice invocation currently makes it slower than desired; a real performance design needs a guarded first-use loader/cache hit.
- Keep `adpcm`, `portrait-adpcm`, and `all-seven` normal builder profiles quarantined. Continue P0 issue #46, do not ship this prototype.

The previous `$8F51` combined candidate was **rejected** after the unmodified game was proven to read, write and execute that live BSS. The new code is on CD and in a separately mapped RAM bank; it does not silently re-label source-zero in a live module as free space.
