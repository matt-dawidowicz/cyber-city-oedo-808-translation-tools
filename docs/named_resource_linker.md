# Named-resource linker and KURUZER relocation

Status: Mission 0-B loader contract statically proven and source-guarded;
`KURUZER` move and growth live-tested in MesenCE 2.2.1 through the opening.
Diagnostic only — no release profile enables relocation yet.

This is the first step of the Definitive Edition resource linker: a rebuilt
resource is written to new sectors at its natural size and the game's own
descriptor is repointed at it, instead of squeezing English into Japanese
byte budgets.

## Descriptor tables

Every mission overlay embeds a table of 16-byte descriptors at CPU `$5D4B`
(Mission 0-B: payload `0x0013754B`, 48 entries, SHA-256
`502d5119fc3ab0cf1cd21bef68221f46008f4003868601ab49ca1399bfc4fb1b`).
A whole-payload scan finds 13 such tables.

| Bytes | Meaning as read by the Mission 0-B loader |
|---|---|
| 0-8 | NUL-padded ASCII name |
| 9 | LBA high byte |
| 10-11 | LBA low/middle bytes (absolute disc LBA) |
| 12 | sector span — **not read** by this loader |
| 13-14 | byte length (16-bit) |
| 15 | length high byte — **not read** by this loader |

`KURUZER` is `LBA $10F1`, span 1, length `0x320` (800 bytes). The earlier
note that it spans eight sectors up to `MAYA01` was wrong: the next table
entry in disc order is `MARKETT` at `$10F5`, and the dense data in
`$10F2-$10F4` is not free space.

## Loader and heap contract (Mission 0-B)

```text
$8F90  heap pointer $2778/$2779 -> $06/$07
$8F9A  JSR $6CCB          load named resource at heap pointer
$6CF7    JSR $6E36        walk $5D4B table in 16-byte steps, match name
$6D1F    dest + length >= $D800 -> fail (compaction at $9BBA, then retry)
$6D30    claim one of 16 resident-cache slots at $34A9
$6D7C    JSR $6EA0        CD read: LBA, 16-bit length
$6DA8    JSR $420C        copy down by 16 bytes (strip resource header)
$8FA5  heap pointer += length - 16
$40CE  heap base initialised to $C000
```

Consequences for relocation:

1. A resource can move anywhere on Track 2 by changing descriptor bytes 9-15.
2. A rebuilt resource may grow while `load address + length < $D800`.
3. The 16-byte header is loaded and then stripped; keep it unchanged.
4. Compaction relocates resident resources, so the game cannot hold absolute
   RAM pointers into a resource across loads.

Source guards for each of these instructions live in
`cyber_oedo/disc/named_resources.py`.

## Linker window

Track 2 relative sectors 41049-41198 are authenticated zero fill. The English
pool and VWF experiments claim 41049-41068 and PR #53 claims 41190, so the
linker owns **41120-41189** only. `relink_named_resource` refuses any target
sector that is non-zero or named by any descriptor-shaped record anywhere on
the disc, and refuses a resource whose header changed or whose length would
exceed the heap bound at its observed load address.

## Live evidence (2026-11-04)

MesenCE 2.2.1, Japanese Super CD-ROM System 3.0 BIOS (SHA-256
`e11527b3…d9ce`), original CloneCD set, opening controller schedule from
`mesen_p0_natural_npc_regression.lua`, read-only probe
`tools/mesen_named_resource_heap_probe.lua`.

| Run | KURUZER LBA | Length | Load at | Heap after | Compactions |
|---|---|---|---|---|---|
| original | `$10F1` | `0x320` | `$C350` (frame 2470) | `$C660` | 0 |
| `move` | `$AEA6` | `0x320` | `$C350` | `$C660` | 0 |
| `grow` | `$AEA6` | `0x5D6` | `$C350` | `$C916` | 0 |

`INIT` loads first at `$C000`; no other named resource loads through frame
8,700.

Screenshots at fixed frames:

- `move` is ~41 frames late at first (seek to the end of the disc), then is
  byte-identical to the original at every captured frame from 5,000 to 8,600.
- `grow` shows the narration twice (still on the second copy at frame 6,000),
  fades out through the post-narration scene commands at 7,000, and is
  byte-identical to the original street scene at 8,000 and 8,600.

So the commands after the narration in `KURUZER` do not depend on fixed
offsets that the growth would have shifted, at least along the opening path.

## Build commands

```bash
cyber-oedo build-relocation-test source.ccd out-move --mode move
cyber-oedo build-relocation-test source.ccd out-grow --mode grow
```

Each build authenticates the source set, changes exactly two sectors
(descriptor sector LBA 4212 and the new resource sector), rebuilds Mode-1
EDC/ECC, verifies the whole image, and writes `relocation_manifest.json`.

## Not yet established

- Other overlays' loaders and heap bases (only Mission 0-B is guarded).
- Whether any later scene reloads `KURUZER` (cache eviction, save/reload).
- Real hardware seek behaviour; the end-of-disc placement costs ~0.7 s in
  Mesen and should move to a better optical position once layout is planned.
- English narration through the release text engine; this test grows the
  Japanese narration only.
