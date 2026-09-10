# Modernization roadmap

## Goal

Keep the repository small, reproducible, and evidence-driven while the game is
reverse-engineered into a translation-safe model. Software cleanup must not
change authenticated game bytes merely for architectural neatness.

## Current state

| Area | Status | Purpose |
|---|---|---|
| Package migration | In cleanup | One canonical `cyber_oedo` implementation surface |
| Tier A | Complete | Structural extraction, bytecode, resources, inventory |
| Tier B1 | Complete | Mission 0 dialogue interpreter proof |
| Tier B2 | Complete | Indexed table loader and state-selector proof |
| Tier B2.5 | Complete | Bank-aware frozen live-snapshot validator |
| Tier B live certification | In progress | Runtime state, glyph and VDC evidence |
| Tier B3 | Gated | Translation-safe runtime/storage architecture |
| Tier C | Future | Complete compiler, relocation and release build |

## Maintenance track

### 1. Remove transitional architecture

- retire root-level compatibility scripts after package imports are canonical;
- remove subprocess command fallback and duplicated command registries;
- remove failed Stage-1 wide-renderer implementation code;
- remove completed/disproven exploratory scanners from the shipped surface;
- keep historical failure evidence in documentation and Git history.

### 2. Decompose build profiles

The legacy `build/engine.py` accumulated translation data, layout rules,
encoding, graphics integration, source identity, and profile assembly in one
large module. Split those responsibilities into typed profile/data modules and
small mechanisms while preserving the exact patch plan.

Target shape:

```text
cyber_oedo/
|-- build/
|   |-- pipeline.py
|   |-- plan.py
|   |-- source.py
|   |-- manifest.py
|   |-- verification.py
|   `-- profiles/
|       |-- mission0_stock.py
|       |-- startup.py
|       |-- dossiers.py
|       `-- media_mix.py
|-- text/
|   |-- fullwidth.py
|   `-- layout.py
|-- runtime/
|-- script/
|-- resources/
`-- disc/
```

### 3. Keep public contracts narrow

The supported operator interface is `cyber-oedo` / `python -m cyber_oedo` plus
versioned generated schemas. Internal Python module paths may evolve while the
reverse engineering is active; avoid promising broad compatibility aliases.

### 4. Use modern quality tooling

Use Ruff for generic Python correctness/style checks and unit tests for
project-specific invariants. CI should test the minimum supported Python and a
current Python on every pull request, with the Windows/Linux matrix available
for release or manual validation.

## Reverse-engineering track

The technical rationale and translation policy are documented in
`game_architecture_and_translation_strategy.md`.

### Tier A — structure

Authenticate source media, model formats conservatively, preserve offsets and
controls, and make extraction round-trip where possible.

### Tier B — runtime meaning

Prove overlay mappings, interpreter behavior, state tables, pointers, glyph
paths, and resource lifetime. Live evidence must include the MPR context needed
to disambiguate reused HuC6280 logical addresses.

### Tier C — translation mutation

Activate longer-text storage, relocation, or renderer work only after the
relevant Tier-B ownership and reachability gates are satisfied. Every mutation
must remain source-guarded and bounded to an explicit patch plan.

## Release gate

Before any cleanup or refactor is promoted as behavior-preserving:

1. synthetic regression tests pass;
2. packaging and command smoke tests pass;
3. authenticated analysis artifacts retain their expected identities where the
   changed code is not intended to alter them;
4. the stock-renderer patch plan is byte-equivalent; and
5. any deliberate output change is separately documented and reviewed.

Modernization is successful when it reduces the amount of code a maintainer
must understand without reducing the amount of evidence required to change the
game.
