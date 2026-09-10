# Cyber City Oedo 808 translation toolkit

This repository is a reproducible reverse-engineering and English-translation
toolkit for the Japanese PC Engine CD release of *Cyber City Oedo 808: Kemono
no Alignment*.

The project is deliberately evidence-driven. The original game does not expose
a single script format or text engine: it loads overlays into reused HuC6280
logical addresses, mixes several text/resource formats, and keeps some dynamic
names and labels in mutable runtime tables. For that reason, finding Japanese
text is not enough to prove how it is reached, rendered, or safely expanded.

The project therefore separates structural extraction, runtime proof, and final
binary mutation into tiers. See
[`docs/game_architecture_and_translation_strategy.md`](docs/game_architecture_and_translation_strategy.md)
for the technical rationale and the translation policy relative to the OVA.

## Project status

| Tier | Status | Scope |
|---|---|---|
| Tier A | Complete | authenticated structure, dialogue bytecode, resources, inventory |
| Tier B1 | Complete | Mission 0 dialogue-interpreter proof |
| Tier B2 | Complete | indexed record-table loader and state selector |
| Tier B2.5 | Complete | bank-aware live-snapshot validation tooling |
| Tier B live certification | In progress | live state, glyph/font, and VDC evidence |
| Tier B3 | Gated | safe English storage/renderer architecture |
| Tier C | Future | complete translation compiler and release build |

The existing `mission0-stock-renderer` build remains a guarded vertical slice,
not a full translation. It uses the game's stock fullwidth Shift-JIS renderer
and does not activate the failed Stage-1 wide-text experiment.

## What is confirmed

- Track 2 contains 41,199 Mode 1 data sectors.
- The extracted Track 2 payload is 84,375,552 bytes.
- Its SHA-256 is
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.
- Dialogue records begin with `27 28` and end with a context-aware `00`
  terminator.
- Low bytes inside dialogue are bytecode controls or operands, not generally
  safe ASCII.
- The Mission 0 dialogue interpreter is mapped and source-guarded.
- `3D` is a two-operand indexed record-field insertion command in that
  interpreter.
- The indexed table is loaded into `$A400` as 24 fixed 32-byte records; each
  record contains primary and alternate text slots plus runtime state.
- `2F <index>` can update the state byte used by `3D` to select the displayed
  field.
- The original stock renderer uses the System Card font service and a confirmed
  11-cell ordinary dialogue width in the mapped Mission 0 path.
- Standard Mode 1 EDC/P-Q ECC regeneration is implemented and tested.

Claims that are not yet runtime-proven remain explicitly marked as hypotheses.
In particular, zero-filled or padding-like bytes are not treated as writable
space merely because they look unused.

## Translation policy

The game shares the *Cyber City Oedo 808* setting and principal cast with the
OVA, and the English OVA is the most familiar English-language reference for
many players. The translation therefore uses established franchise names and
terminology where they fit the game, while treating the Japanese game text as
the primary source.

In practice:

- retain familiar names such as Sengoku, Benten, Gogul, Hasegawa, Okyo, and
  Varsus when supported by the game;
- write natural English that preserves characterization rather than Japanese
  syntax;
- use the English OVA as a continuity and tonal reference, not as a replacement
  script;
- do not import dub-only jokes, profanity, or plot information unless the game
  itself supports them; and
- preserve game-specific state changes, including generic descriptors that
  later become character names.

The intended result is an English release that feels consistent with the OVA
world while remaining a translation of this game.

## Installation

Python 3.11 or newer is supported.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Core binary reconnaissance uses NumPy and Numba for the 84 MiB payload scanners.
Pillow is optional for graphics work and is included in the `graphics` and
`dev` extras.

The supported operator interface is the installed command:

```bash
cyber-oedo --help
```

or equivalently:

```bash
python -m cyber_oedo --help
```

Historical root-level `python script.py ...` wrappers have been retired. New
code and automation should use package commands and `cyber_oedo.*` modules.

## Canonical analysis pipeline

```text
CloneCD IMG
    |
    v
cyber-oedo extract-track2-mode1
    |
    v
Track 2 payload
    |
    v
cyber-oedo analyze
    |
    +--> resource_map.tsv
    +--> likely_sjis.tsv
    +--> dialogue.tsv
    +--> auxiliary.tsv
    +--> translation_inventory.tsv
    +--> analysis.sqlite3
```

Typical invocation:

```bash
cyber-oedo extract-track2-mode1 source.img track02_mode1_2048.bin
cyber-oedo analyze track02_mode1_2048.bin --output-dir analysis
```

`analyze` maps the payload once for the payload-dependent Tier-A stages and
keeps the established TSV contracts. The individual `build-resource-map`,
`scan-likely-sjis`, `extract-dialogue`, `extract-auxiliary-text`,
`build-translation-inventory`, and validation commands remain available for
forensic/debug use. `scan-track` is optional broad reconnaissance rather than a
required translation-pipeline stage.

The generated inventory keeps binary occurrences separate even when visible
Japanese repeats. Translators normally edit only `english_translation` and
`translator_notes`; offsets, controls, source bytes, and structural fields are
generated evidence.

## Runtime proof commands

Static/source-guarded Tier-B evidence:

```bash
cyber-oedo prove-dialogue-runtime track02_mode1_2048.bin \
  --dialogue dialogue.tsv --output tier_b_runtime.json
```

Bank-aware frozen live snapshot validation:

```bash
cyber-oedo prove-live-dialogue-snapshot registers.json memory.bin \
  --output live_3d_proof.json
```

The live validator requires the stopped PC, accumulator, all eight HuC6280 MPR
values, and a complete 64 KiB logical memory dump. It rejects a reused logical
address if the expected Mission 0 bank is not mapped.

## Guarded human-test build

The existing stock-renderer vertical slice is built from a user-supplied,
authenticated CloneCD set:

```bash
cyber-oedo build-human-test-disc source.ccd output-directory
```

Use `--title-screen original` to retain the original opening art.

The builder:

1. authenticates the supplied CCD/IMG/SUB set;
2. copies it to an isolated output directory;
3. validates exact source bytes for every planned patch;
4. applies same-size reviewed payload changes;
5. rebuilds Mode 1 EDC/ECC for affected sectors;
6. compares the complete source/output raw images; and
7. writes a machine-readable manifest.

The source media is never modified in place.

## Current package layout

```text
cyber_oedo/
|-- analysis/      scanners, disassembly, resource analysis
|-- allocation/    explicit owned-region allocation models
|-- build/         authenticated planning, pipeline, verification
|   `-- profiles/  typed stock-build data grouped by concern
|-- commands/      small automation/report commands
|-- contracts/     versioned generated-data contracts
|-- disc/          CloneCD/Mode-1 geometry and patch primitives
|-- graphics/      PC Engine tile and title tooling
|-- resources/     resource candidate/evidence models
|-- runtime/       Tier-B source and live-runtime proof
|-- script/        typed dialogue bytecode
`-- text/          extraction, layout, inventory, relocation
```

See [`docs/package_layout.md`](docs/package_layout.md) and
[`docs/architecture.md`](docs/architecture.md) for ownership rules.

## Safety and data policy

The repository contains code, documentation, and synthetic tests. It does not
ship the game image, extracted full payload, BIOS, audio tracks, or generated
full text dumps. Supply legally obtained source media locally.

Do not hex-edit the authenticated source IMG. A candidate pointer, repeated
fill byte, or apparently empty region is evidence to investigate, not ownership
permission.

## Development

Before committing:

```bash
python -m ruff check cyber_oedo tests benchmarks
python -m unittest discover -s tests -v
python -m compileall -q cyber_oedo tests benchmarks
python -m cyber_oedo doctor
```

CI runs the maintained suite on Python 3.11 and 3.13 for pull requests, builds
source/wheel distributions, and smoke-tests the installed wheel outside the
checkout.

Further documentation:

- [`docs/game_architecture_and_translation_strategy.md`](docs/game_architecture_and_translation_strategy.md)
- [`docs/tier_a_architecture.md`](docs/tier_a_architecture.md)
- [`docs/tier_b_runtime.md`](docs/tier_b_runtime.md)
- [`docs/text_format.md`](docs/text_format.md)
- [`docs/disc_layout.md`](docs/disc_layout.md)
- [`docs/build_architecture.md`](docs/build_architecture.md)
- [`docs/development.md`](docs/development.md)
- [`docs/modernization_roadmap.md`](docs/modernization_roadmap.md)
- [`docs/stage1_runtime_failure.md`](docs/stage1_runtime_failure.md)
