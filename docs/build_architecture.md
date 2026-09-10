# Authenticated build architecture

The maintained human-test build separates profile data, planning, source
handling, mutation, and verification. This prevents translation edits from
silently changing the disc trust boundary and prevents low-level binary code
from owning game-specific prose.

## Layers

### Profile data

`cyber_oedo.build.profiles` contains immutable definitions for the current
`mission0-stock-renderer` vertical slice.

- `models.py` — typed same-size text/layout patch descriptions;
- `startup.py` — startup, mission-title, and Mission 0 text;
- `dossiers.py` — opening criminal dossier content/layout;
- `media_mix.py` — Media Mix content/layout;
- `mission0_stock.py` — profile assembly, source hashes, title contracts, and
  reviewed sector-footprint helpers.

The former monolithic `build/engine.py` has been retired. No single build module
should again combine translation data, binary I/O, CLI behavior, and output
verification.

### Planning

`cyber_oedo.build.plan` creates a deterministic source-independent patch plan.
Each entry records category, label, payload offset, byte count, source SHA-256,
and replacement SHA-256 without serializing copyrighted source bytes.

`cyber_oedo.build.verification` independently checks plan shape and guarded
sector footprint against the selected profile.

This planning boundary makes architectural refactors reviewable before a disc is
opened: a supposedly behavior-preserving change should retain the intended
profile entries and footprint.

### Source authentication and copy isolation

`cyber_oedo.build.source` locates the CloneCD companions, verifies the complete
source identities, and creates the disposable output set.

Authenticated input is evidence and must remain immutable.

### Mutation

`cyber_oedo.disc.patching` applies guarded payload patches to the copied IMG and
rebuilds every affected raw Mode 1 sector. The patch layer operates from exact
expected bytes; it does not infer game-specific free space or ownership.

### Pipeline

`cyber_oedo.build.pipeline` orchestrates:

1. source authentication;
2. isolated source copy;
3. optional title-profile materialization;
4. text/binary patch collection;
5. guarded Mode 1 patch application;
6. replacement readback;
7. complete raw-image comparison;
8. CCD/SUB preservation checks;
9. manifest generation; and
10. atomic installation of the finished output directory.

A failure removes the temporary build rather than leaving a partially patched
result at the requested destination.

### Manifest and image verification

`cyber_oedo.build.manifest` serializes reviewed patch metadata.
`cyber_oedo.build.image_verify` compares source/output images efficiently and
verifies exact replacement bytes.

Large binary source/replacement regions are identified by digest rather than
embedded wholesale in generated evidence.

### Public command

`cyber_oedo.build.human_test` is intentionally thin. It owns argument parsing and
human-readable command output, then delegates the actual build to the package
pipeline.

Use:

```bash
cyber-oedo build-human-test-disc source.ccd output-directory
```

## Current stock-renderer boundary

The vertical slice intentionally stays within the game's established fullwidth
Shift-JIS rendering behavior. It contains no active Stage-1 global escape-marker
renderer patch.

Longer-text relocation and any future compact/halfwidth renderer belong to a
later Tier-C build only after Tier-B runtime evidence establishes the necessary
access, storage, and rendering contracts.

## Refactor safety

A build refactor is not allowed to claim success merely because unit tests pass.
When the authenticated source set is available, behavior-preserving build
changes should also reproduce the reviewed patch plan/sector footprint and pass
the full copy/patch/readback/image-comparison workflow.

The build system's purpose is not just to produce a bootable image. It is to
make every changed byte attributable to a reviewed translation or binary patch
under an explicit source guard.
