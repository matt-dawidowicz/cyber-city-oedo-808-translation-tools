# Authenticated build architecture

The human-test builder now has an explicit planning boundary in front of the
preserved authenticated build engine.

## Layers

`cyber_oedo.build.plan` owns a deterministic, source-independent description of
the complete patch profile. It records category, label, payload offset, byte
count, source SHA-256, and replacement SHA-256. It never serializes copyrighted
source bytes.

`cyber_oedo.build.verification` independently checks plan identity, digest
shape, and guarded-sector footprint against the build engine's reviewed profile
helper.

`cyber_oedo.build.human_test` is the public orchestration facade. Every build
must produce and verify the selected profile plan before the authenticated disc
engine is allowed to run.

`cyber_oedo.build.engine` retains the mature source authentication, CloneCD
copy isolation, exact-byte guards, Mode 1 EDC/ECC rebuilding, whole-image
comparison, manifest creation, and failure cleanup. Moving that proven logic
without simultaneously changing it keeps the trust boundary auditable.

The historical `build_human_test_disc.py` file is now only a compatibility shim
for imports and direct script invocation.

## Plan identity

A patch plan has canonical JSON and its own SHA-256 identity. That makes
infrastructure refactors reviewable independently from a generated disc image:
if a change is claimed to be structural, the plan digest and guarded-sector
footprint should remain stable for the same build profile.

The optional clean title is represented without reading a disc because the
reviewed source title and palette SHA-256 values are already part of the build
contract. Replacement identities are computed from the deterministic generated
assets.

## Safety boundary

The planning layer does not weaken or replace source authentication. The build
engine still reads the user's source image, verifies the complete source set,
checks exact guarded bytes, applies patches only to an isolated copy, rebuilds
EDC/ECC, compares every raw sector, and rejects unexpected changes.
