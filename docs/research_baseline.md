# Research baseline after restart

This document preserves findings that remain useful independently of the old
translation prototype. It intentionally excludes implementation milestones,
working translations, and patch-profile decisions.

## Authenticated source identity

The analyzed CloneCD set has these SHA-256 identities:

| File | SHA-256 |
| --- | --- |
| CCD | `716e509edaeeddc1b12c827ada3579b15c612a5f16400b72dabad2c6bcfece1b` |
| IMG | `815a8dda33ba2bb046fcbde773ad3a80fc6f89a96ef07e9c06bcc1c2e5fddece` |
| SUB | `ae8f54a4cd83e5e985d975f29654f8aa2f384cb4f7dcbd16a39b05b3263db411` |

The extracted Track 2 Mode 1 payload is 84,375,552 bytes with SHA-256
`0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.

## Disc structure

- 88 tracks total: one program/data track and 87 audio tracks.
- Track 2 INDEX 01 begins at absolute LBA 3,590.
- The valid Track 2 Mode 1 range contains 41,199 sectors, relative sectors
  0 through 41,198.
- The corresponding absolute range is LBA 3,590 through 44,788.
- Track 3's pregap occupies LBA 44,789 through 44,938.
- The PC Engine CD header identifies a 16-sector boot program beginning at
  Track 2 relative sector 3, loaded and executed at `$4000`.

## Text representation

Observed main dialogue is ordinary Shift-JIS rather than a compressed text
stream. Candidate records use marker bytes `27 28`, contain Shift-JIS glyphs
mixed with single-byte control values, and terminate with `00`.

Low values in the ASCII range cannot be treated as ordinary ASCII inside these
records. They occur as control/layout bytecode and must remain opaque until
runtime semantics are proven.

The boot program calls the System Card BIOS `EX_GETFNT` service at `$E060`,
which is relevant to the original 16x16 glyph path.

## Resource structure

The data track contains sector-aligned ASCII resource names and repeated
engine/resource anchors. The anchors recorded by the current layout model occur
at relative sectors:

`5376`, `11047`, `16554`, `20924`, `25371`, `29334`, `32831`, `36132`, and
`39435`.

Constant-fill tails near named resources are useful reconnaissance evidence,
but they do not prove that the bytes are unreferenced or safe for relocation.

The preserved `docs/evidence/kuruzer_relocation_evidence.json` records one
important negative result: the opening narration was found inline in `KURUZER`,
but no aligned pointer table or owned relocation destination was proven. That
hypothesis must not be treated as authorized relocation space without new
evidence.

## What is deliberately unresolved

A new translation implementation still needs reproducible answers for:

- runtime semantics of dialogue controls across all relevant resource types;
- which extracted records are reachable and player-visible;
- resource loading and destination ownership;
- pointer/length fields and aliases that govern dialogue resources;
- safe capacity or relocation strategy for longer English text; and
- the release-quality English rendering path.

The restart exists so these questions can drive the next architecture instead
of being constrained by the removed prototype.
