# P0 cold-boot witness replay: 2026-10-20

This document describes a source-backed **single natural street-watcher encounter** in
MesenCE 2.2.1 (Linux), run with the authenticated CloneCD triplet, Japanese
System Card 3.0, and the game's original 88-track CUE layout. The test uses
ordinary controller input, no savestate, forced PC, or gameplay-memory writes.

## Reproduction

- `tools/mesen_p0_natural_npc_regression.lua` on the original disc and a
  source-authenticated English/VWF pilot with `performance_experiment=none`.
- `tools/mesen_p0_portrait_cache_regression.lua` on a separate
  `--performance-experiment portrait --acknowledge-unsafe-performance` disc.
- Controller sequence is identical for all three: run/intro taps before frame
  8600; right through frame 13299; up through 15599; right and intermittent
  I through 15999; **release I from 16000 onwards**.
- Both scripts place screenshots in their own script-data folders. The
  portrait-only script checks the mapped 12-byte cave prefix at `$4CFA`,
  rather than inferring patched residency from an unpatched disc.
- Each session terminates at frame 17900 with exit code 0 and
  `late_ADPCM=1 natural_portrait=1 ... success=true`.

## Independent screenshots

All seven PNG files compared **byte-for-byte identically across original,
portrait-only, and English/VWF no-performance variants**:

| Frame | PNG SHA-256 |
| --- | --- |
| 6000 | `cf365fae13a5f979ba99d995dd496ed9ea8977238a3cdf8f07608730c07d0d7` |
| 8600 | `cf365fae13a5f979ba99d995dd496ed9ea8977238a3cdf8f07608730c07d0d7` |
| 13300 | `61e077f610355fc65e112d63495ce0492063ef9bda632056404781496b766632` |
| 15600 | `9ba5aca460ad76b0367bce4112df44be8430334836199f5ec2052536de1939f9` |
| 16500 | `4c040b913bee5997a46310c5c81969500db13819ef70d999e5e1dd35c8d63e2f` |
| 17000 | `4c040b913bee5997a46310c5c81969500db13819ef70d999e5e1dd35c8d63e2f` |
| 17800 | `4c040b913bee5997a46310c5c81969500db13819ef70d999e5e1dd35c8d63e2f` |

All three saw the shared ADPCM call at frame 15955 (logical `$80E0`)
and the natural portrait-loader entry at frame 15975 (logical `$8405`).
In the portrait-only run, the mapped prefix at `$4CFA` was
`43 01 48 43 20 48 43 40 48 A9 68 53`. In the other two,
`$4CFA` remained zero-filled. All runs had equivalent observed MPRs
at these checkpoints.

The research-branch synthetic unit suite also passed 413 tests.
The builder correctly rejected `adpcm`, `portrait-adpcm`, and
`all-seven` profiles **even with unsafe acknowledgment**, reporting
unverified cross-overlay ADPCM residency and an overlapping cave.

## Scope and remaining P0 gates

This strengthens the portrait-only regression witness and confirms that
freezing Button I at frame 16000 eliminates input-induced timing differences.
It **does not** establish that the real Mission-0-B bartender was reached,
that the dialogue fully completed or a second interaction succeeded, that
scene return and ADPCM restoration match stock, or that later overlay cache
ownership is valid.

Issue #46 remains **OPEN**. Do not enable any combined ADPCM performance
profile or promote a release until these separate gates are proven. The
historic `$4CFA` portrait/ADPCM cave collision remains a safety block.
