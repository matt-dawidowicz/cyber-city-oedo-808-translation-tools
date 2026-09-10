# Package layout

The repository has one canonical implementation tree: `cyber_oedo/`.
Root-level compatibility modules and failed experimental command surfaces have
been retired. The installed `cyber-oedo` command is the supported operator
entry point.

## Namespaces

```text
cyber_oedo/
|-- allocation/
|-- analysis/
|-- build/
|   `-- profiles/
|-- commands/
|-- contracts/
|-- disc/
|-- graphics/
|-- resources/
|-- runtime/
|-- script/
`-- text/
```

### `allocation`

Models explicit owned regions and allocation requests. Allocation must fail
closed when capacity, ownership, source identity, or overlap constraints are
not proven.

### `analysis`

Contains broad reconnaissance, resource/text analysis, and HuC6280 diagnostic
disassembly. Heuristic scanners may identify candidates; they do not establish
reachability or permission to patch.

### `build`

Owns deterministic patch planning, authenticated source-copy orchestration,
Mode 1 patch application, manifests, and final verification.

`build/profiles/` contains immutable game-specific vertical-slice data separated
by concern:

- `models.py` — typed same-size text/layout patch descriptions;
- `startup.py` — startup, mission-title, and Mission 0 stock text;
- `dossiers.py` — opening dossier content/layout;
- `media_mix.py` — Media Mix content/layout;
- `mission0_stock.py` — profile assembly and title/source contracts.

The former 91 KiB `build/engine.py` monolith has been decomposed so profile data,
text/layout models, binary I/O, and orchestration no longer share one module.

### `commands`

Small automation/report commands that compose package APIs. Commands should not
be alternate implementations of the underlying library behavior.

### `contracts`

Versioned schemas and external data-contract metadata.

### `disc`

Game-agnostic and title-specific disc geometry, CloneCD handling, raw Mode 1
integrity, Track 2 extraction, and guarded payload patch primitives.

### `graphics`

PC Engine tile codecs, generated title assets, renderers, and contact-sheet
helpers. Pillow-dependent functionality remains optional.

### `resources`

Candidate resource boundaries, evidence, and ownership metadata. Candidate
regions remain distinct from proven writable regions.

### `runtime`

Tier-B runtime evidence: source-guarded interpreter/table analysis and
bank-aware live-snapshot validation.

### `script`

Typed dialogue-bytecode parsing and serialization. Operand width is part of the
format model; a zero byte cannot be interpreted independently of command
context.

### `text`

Structured/auxiliary extraction, translation inventory, stock-renderer layout,
and guarded relocation mechanics.

Text layout and pointer/storage relocation are deliberately separate concerns:
layout can be tested without claiming storage ownership, while relocation
requires explicit pointer and destination evidence.

## Import policy

All internal imports must use `cyber_oedo.*` package paths. Package modules may
not depend on retired root-module names.

The test suite contains an architectural regression check that rejects the
return of those dependency edges.

## Public surface

The durable public surface is:

- `cyber-oedo <command>`;
- `python -m cyber_oedo <command>`; and
- documented/versioned generated file schemas.

Internal Python module paths are engineering implementation details while
reverse engineering is still active. New compatibility shims should be added
only for a demonstrated external consumer, not preemptively.

## Historical code

Disproven Stage-1 wide-renderer code and reversed-SJIS reconnaissance code are
not shipped as supported modules. The Stage-1 runtime failure remains documented
because it establishes an important negative result: global escape-marker
assumptions are unsafe in this game's overlay/resource architecture.

Git history remains the source for obsolete implementations if they are ever
needed for forensic comparison.
