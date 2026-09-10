# Development and maintenance guide

## Supported architecture

The repository has one maintained Python implementation surface: the
`cyber_oedo` package.

Operators should use either:

```bash
cyber-oedo <command> ...
```

or:

```bash
python -m cyber_oedo <command> ...
```

Historical root-level script wrappers were transitional migration scaffolding
and are no longer part of the supported architecture. Package code must not
import them or recreate equivalent duplicate modules.

## Environment

Create an editable development environment with:

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The core package requires NumPy and Numba because the reconnaissance scanners
process the complete 84 MiB Track 2 payload in compiled/vectorized hot loops.
Pillow is optional for graphics commands and is provided by the `graphics` and
`dev` extras.

`pyproject.toml` is the authoritative dependency declaration. Do not add a
second `requirements.txt` dependency surface.

## Daily quality gate

Run:

```bash
python -m ruff check cyber_oedo tests
python -m unittest discover -s tests -v
python -m compileall -q cyber_oedo tests
python -m cyber_oedo doctor
```

Before packaging or command-surface changes, also run:

```bash
python -m build --outdir dist
```

Ruff handles generic Python correctness/style checks. Unit tests should encode
project behavior and architecture, not reimplement a general-purpose linter.

## CI

Pull requests run the maintained checks on Ubuntu with both Python 3.11 and
3.13. CI also builds source and wheel distributions and force-installs the wheel
outside the checkout before running `python -m cyber_oedo --help` and `doctor`.
This prevents an editable checkout from hiding missing package files.

A Windows/Linux compatibility matrix remains available for manual/release
validation.

## Package ownership

Use package imports that reflect the actual responsibility:

- `cyber_oedo.disc` for CloneCD geometry, Mode 1 integrity, extraction, and raw
  patch primitives;
- `cyber_oedo.script` for typed dialogue bytecode;
- `cyber_oedo.text` for text extraction, layout, inventory, and relocation;
- `cyber_oedo.resources` for resource evidence;
- `cyber_oedo.runtime` for Tier-B static/live runtime proof;
- `cyber_oedo.graphics` for PCE tile/title tooling;
- `cyber_oedo.build` for patch planning, authenticated builds, manifests, and
  verification;
- `cyber_oedo.build.profiles` for immutable game/profile-specific patch data.

Avoid catch-all modules. If a file combines large translation datasets with
I/O, binary mutation, presentation, and CLI behavior, split those concerns
before adding more functionality.

## Build-profile changes

The stock build is deliberately decomposed:

- `build/profiles/models.py` owns typed patch/data models;
- `build/profiles/startup.py` owns startup, mission-title, and Mission 0 text;
- `build/profiles/dossiers.py` owns opening dossier content/layout;
- `build/profiles/media_mix.py` owns Media Mix content/layout;
- `build/profiles/mission0_stock.py` assembles the maintained vertical-slice
  profile;
- `build/plan.py` produces source-independent patch plans;
- `build/pipeline.py` performs authenticated copy/patch/verification work.

A profile-data edit should not require touching raw-sector machinery. A
raw-sector implementation change should not require editing translation data.

## Real-disc validation gate

Synthetic tests cannot prove title-specific disc behavior. Run authenticated
local validation when a change touches:

- source hashes or CloneCD path handling;
- raw/payload coordinate conversion;
- expected or replacement bytes;
- EDC/ECC regeneration;
- dialogue record semantics;
- resource boundaries or relocation logic;
- title/palette insertion; or
- runtime-engine mutation.

For analysis changes, compare old/new generated artifacts: record counts, offset
sets, schemas, and stable hashes where available.

For build changes, compare the deterministic patch plan before producing a disc
and then compare the final raw-sector footprint. A cleanup/refactor must not
silently broaden the changed sector set.

## Reverse-engineering discipline

Do not convert observations into stronger claims than the evidence supports.
In particular:

- string occurrence does not prove runtime reachability;
- padding does not prove writable ownership;
- zero-filled code/data space is not automatically a code cave;
- a logical HuC6280 address is ambiguous without its MPR mapping;
- emulator bootability does not replace exact source guards or structural
  verification.

Tier A owns structural facts. Tier B owns runtime semantics and ownership/lifetime
proof. Tier C may activate translation mutations only after the relevant Tier-B
gates are satisfied.

See `game_architecture_and_translation_strategy.md` for the rationale.

## Translation changes

Translation wording and reverse-engineering mechanics should remain separable.
Translator-facing text belongs in the inventory/profile data with notes and
context; engine code should not contain ad hoc prose substitutions.

Use the OVA for established continuity, terminology, and characterization where
appropriate, but translate the Japanese game source. Do not import dub-only
rewrites simply to make the game resemble the English dub.

## Removing code

Prefer deletion over permanent compatibility scaffolding when an experiment is
finished or disproven. Git history is the archive.

Historical failure documentation can remain when it prevents repetition of a
bad design; executable implementations of abandoned designs should not remain
registered as supported commands.
