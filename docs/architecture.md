# Architecture and extension guide

## Design goals

This toolkit is designed for auditable reverse engineering rather than fast,
opaque patch production. Each layer should make its evidence and coordinate
system explicit so a future translation change can be traced back to the
original authenticated bytes and, where necessary, live runtime behavior.

Core principles:

1. never modify authenticated source media in place;
2. name every coordinate system and bank mapping;
3. separate format facts from discovery heuristics;
4. preserve raw evidence next to decoded interpretations;
5. distinguish occurrence, reachability, ownership, and patch safety;
6. keep abandoned experiments out of the maintained command surface;
7. prefer deterministic plans and fail-closed mutations; and
8. require stronger evidence as a change gets closer to modifying the game.

## Why the game requires this architecture

The original game is not organized around one script container or renderer.
CD-loaded overlays reuse HuC6280 logical addresses under different MPR mappings,
text appears in multiple unrelated formats, resource-local tables mix visible
strings with state, and apparently spare bytes may have unobserved lifetime or
ownership constraints.

That means several tempting shortcuts are invalid:

- scanning a string does not prove it is used in play;
- seeing the same CPU address twice does not prove the same code is mapped;
- finding repeated fill does not prove free space;
- identifying a byte pattern in dialogue does not make it globally reserved;
- successfully booting a patched image does not prove that unrelated resources
  remain safe.

The Tier A/B/C model exists to restore boundaries that the original game does
not provide cleanly itself. See `game_architecture_and_translation_strategy.md`.

## Layer ownership

### Operator boundary

`cyber_oedo.cli` and `cyber_oedo.registry` expose one package-native command
surface. Registry entries point directly to `cyber_oedo.*` modules; there is no
legacy subprocess dispatch or parallel root-script API.

### Disc layer

`cyber_oedo.disc` owns:

- CloneCD geometry and companion-file handling;
- raw 2352-byte Mode 1 structure;
- 2048-byte payload extraction;
- payload/LBA coordinate conversion;
- EDC/P-Q ECC validation and rebuilding; and
- guarded same-size payload patch primitives.

The low-level patcher is deliberately not responsible for deciding whether a
game-specific region is semantically safe to modify.

### Script layer

`cyber_oedo.script` owns typed dialogue bytecode. Commands have explicit operand
widths, source offsets, and round-trip serialization. This layer fixes the old
class of bugs where an operand value of `00` was mistaken for a record
terminator.

### Text layer

`cyber_oedo.text` owns:

- structured dialogue extraction;
- auxiliary text extraction;
- translation inventory generation/validation;
- stock-renderer fullwidth encoding and page layout; and
- relocation models.

Layout is independent of storage ownership. A page can be compiled and reviewed
without implying that a destination exists. Relocation requires explicit
pointer sites, owned destination bytes, and source guards.

### Resource and allocation layers

`cyber_oedo.resources` records candidate boundaries and evidence.
`cyber_oedo.allocation` operates only on explicit owned regions.

Neither layer may promote a candidate tail or zero-filled span into writable
space merely because it has capacity.

### Runtime layer

`cyber_oedo.runtime` owns Tier-B claims about what the loaded game actually does.
Source-guarded static proof models known interpreter/table code, while live
snapshot validation records PC, registers, memory, and all HuC6280 MPRs needed
to disambiguate overlays.

A live proof artifact must be self-identifying and reproducible. Runtime tooling
is read-only until a separate mutation design has passed its ownership gates.

### Build layer

`cyber_oedo.build` separates immutable profile data from mechanisms:

```text
build/
|-- profiles/
|   |-- models.py
|   |-- startup.py
|   |-- dossiers.py
|   |-- media_mix.py
|   `-- mission0_stock.py
|-- plan.py
|-- source.py
|-- pipeline.py
|-- manifest.py
|-- image_verify.py
`-- verification.py
```

The old build engine mixed translation data, source hashes, layout rules,
graphics, patch definitions, verification helpers, and CLI behavior in one
large module. The decomposed architecture makes each concern independently
reviewable.

`build.plan` creates a source-independent deterministic plan.
`build.pipeline` authenticates/copies source media, applies the selected profile,
verifies outputs, and writes the manifest.

### Graphics layer

`cyber_oedo.graphics` owns tile codecs, title generation, diagnostic rendering,
and related image helpers. Graphics tooling must not become a second binary
patch layer.

## Tier boundaries

### Tier A: structure

Allowed:

- authenticate/extract;
- identify formats and candidate resources;
- parse/serialize bytecode;
- build inventories and databases;
- measure candidates conservatively.

Not sufficient for:

- claiming runtime reachability;
- naming every control semantically;
- claiming free space.

### Tier B: runtime semantics

Allowed:

- source-guarded disassembly;
- overlay/MPR mapping;
- loader/state/pointer proof;
- debugger snapshots and traces;
- renderer/font/VDC observation;
- inactive mutation plans.

Required before active engine/storage changes:

- relevant access path and lifetime;
- pointer/reachability model;
- destination ownership;
- exact hook/source guards;
- renderer behavior at the target context.

### Tier C: safe translation mutation

Tier C may activate relocation or renderer/storage work only after Tier B has
proved the contracts it relies on. Every patch remains bounded, source-guarded,
and independently verifiable.

## Performance policy

Optimize measured hot paths, not every loop indiscriminately.

The full-payload reconnaissance scans use NumPy/Numba because tens of millions
of byte-level iterations dominate runtime. Small metadata transforms and
bounded record operations remain straightforward Python for readability.

Large-file comparisons and patch verification should stream or operate by
changed sectors rather than repeatedly loading full images into memory.

## Testing policy

Use tests for behavior and project-specific architecture:

- exact parsing/serialization;
- coordinate math;
- source-guard failures;
- patch overlap/capacity rules;
- deterministic plan identity;
- known profile footprint;
- package command resolution;
- prohibition on retired root-module imports.

Use Ruff for generic Python correctness/style rather than encoding formatting
preferences as bespoke unit tests.

## Extension rule

When adding a new discovery or translation feature, ask in order:

1. What bytes or runtime state are the evidence?
2. Which coordinate system applies?
3. Is the claim structural, runtime, or mutation-level?
4. Which module owns that claim?
5. What source guard makes failure explicit?
6. What test proves the tool did not broaden its authority?

If those questions do not have clear answers, the feature belongs in research
notes first, not the production patch pipeline.
