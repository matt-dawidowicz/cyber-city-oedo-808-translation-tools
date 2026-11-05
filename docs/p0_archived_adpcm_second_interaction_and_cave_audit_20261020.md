# P0 archived speaker ADPCM-only second-interaction and cave audit (2026-10-20)

**Research evidence only; historical ADPCM cache remains unsafe, isolated, and disabled in ordinary builds.**

## Source-authenticated isolated specimen

Copied the authenticated original `.ccd/.img/.sub` into an **isolated disposable build directory** and installed ONLY the two exact original patches returned by `build_speaker_adpcm_cache_benchmark()`, preserving the portrait loader unmodified. The test image and copyrighted media are NOT committed or distributed.

| Source patch | Track-2 payload offset | Description |
|---|---:|---|
| Shared dialogue module `$80E0` | `0x0030F8E0` | 3-byte JSR to `$4CFA` |
| Mission-0-B cave `$4CFA` | `0x001364FA` | 95-byte historical ADPCM read-through routine |

Patch source signatures were checked before editing. Exactly two raw Mode-1 sectors were modified. Do **not** use this specimen as a release image.

## Completed 26,000-frame MesenCE 2.2.1 replay

The same deterministic stock-controller sequence as `tools/mesen_p0_watcher_second_interaction.lua` was used: natural watcher, select **Move**, return to street, approach and interact a second time, then release I.

The archived ADPCM callsite was `20 FA 4C`, and its mapped `$4CFA` routine began `43 20 48 43 40 48 A9 6B` at ALL THREE direct hook entries:
- frame **2647**: intro; historical cave present
- frame **15955**: first natural watcher; historical cave present
- frame **23430**: **second** natural watcher after moving/returning; historical cave present

The script completed with `source_only_audio_cache=true resident_hits=3`. Final event counts: shared ADPCM=3, portrait loader=2, interaction scans=20, menu I=3, menu II=0. Final normal MPR layout `FF F8 80 81 82 83 84 00`. `AD_READ=3468`, `AD_WRITE=7`; the unpatched source had `AD_WRITE=4` on the same route. These are CPU execution callback counts, **not** a verification that audio waveforms or ADPCM RAM samples match.

**Original versus archived ADPCM-only screenshots:** **36/37 PNG pairs byte-identical**. The only mismatch was frame **23600**, a 44-pixel transient in the dialogue region (bounding box x=131..140, y=161..175). Every other checkpoint was byte-identical, including after the second encounter. A single different frame does not prove a crash or correctness of audio.

## Exact physical code-cave collision and absence of an easy adjacent replacement

Source-authenticated Mission-0-B CPU-address payload region `$4000-$7FFF` contains **one** contiguous zero run long enough for either 95- or 103-byte routine: `[$4C6A,$4D6C)` (258 bytes).

- Repaired portrait cache consumes **`[$4CFA,$4D61)` (103 bytes)**.
- Historical ADPCM cache consumes **`[$4CFA,$4D59)` (95 bytes)**. Their code bodies physically overlap for 95 bytes at the same source offset `0x1364FA`.
- Within that only large zero run, 144 bytes precede portrait, **but the previous portrait code used `$4C93-$4CF9` and that range was observed overwritten during ordinary runtime**. Only 41 source-zero bytes precede this overwritten area; 11 source-zero bytes follow the repaired portrait cave.
- Therefore shifting the old 95-byte ADPCM cave adjacent to the repaired portrait cave **does not provide a verified, resident, contiguous replacement**. Being zero on disc is not sufficient evidence of free ownership. An earlier attempt in an apparently free shared-module area `$90D4` also encountered live runtime data and was discarded.

These facts explain why individually functioning ADPCM and portrait-only specimens do NOT imply they can be composed.

## Requirements for a safe, new combined design

1. Give the ADPCM routine an **independent executable region** with authenticated source ownership and **live** evidence of residency in the shared dialogue module's relevant lifetime. A new destination must not alias the portrait cave or rely on overwritten runtime scratch.
2. Make the global `$80E0` hook **overlay-independent**, or explicitly prove it is removed/guarded whenever Mission-0-B's cave is not mapped. A Mission-0-only trampoline invoked from other missions is inherently unsafe.
3. Preserve original speaker ADPCM transfer registers, RAM source/tag ownership, and exact BIOS return/register/MPR contract; separately compare **real ADPCM bytes and audio output**, not only callback counts.
4. Cold-boot original, portrait-only, ADPCM-only and genuine non-overlapping combined variants through first watcher, Move/return, second watcher, further scenes and missions 1-8. Record first divergences and block release on any unexplained regression.
5. Keep `adpcm`, `portrait-adpcm` and `all-seven` builder profiles hard-quarantined until those gates are met. **Leave issue #46 open.**

See `docs/p0_watcher_move_reentry_20261020.md` for the original versus portrait-only controlled replay and the reason to release Button I after re-entry.
