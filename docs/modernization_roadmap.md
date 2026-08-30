# Modernization roadmap

## Goal

Turn the research repository into a durable engineering toolkit without losing
the properties that make the current reverse-engineering work trustworthy:
explicit coordinates, source authentication, inspectable intermediate files,
synthetic regression tests, and conservative runtime claims.

Modernization should reduce maintenance cost without changing game bytes merely
for architectural neatness.

## Phase 1: stable tooling foundation

Status: implemented by the tooling-foundation modernization.

- Add `pyproject.toml` and an installable package boundary.
- Preserve every root script as a compatibility entry point.
- Add one `cyber-oedo` command that forwards to maintained scripts.
- Add an environment doctor for Python, command modules, and Pillow.
- Run synthetic tests and packaging smoke tests in CI on Windows and Linux.
- Add dependency-update, contribution, security, and release-process metadata.

This phase intentionally avoids touching verified parser and patch behavior.

## Phase 2: move shared libraries into the package

Move reusable implementation modules into clear namespaces while leaving thin
root wrappers in place. A likely target is:

```text
cyber_oedo/
|-- disc/
|   |-- layout.py
|   |-- mode1.py
|   `-- clonecd.py
|-- text/
|   |-- dialogue.py
|   |-- inventory.py
|   |-- validation.py
|   `-- relocation.py
|-- graphics/
|   |-- pce.py
|   `-- title.py
|-- analysis/
|   |-- resources.py
|   `-- disassembly.py
`-- build/
    `-- human_test.py
```

Migration rules:

1. Move one dependency cluster at a time.
2. Keep compatibility imports or wrappers at the old module path.
3. Require the synthetic suite to pass before and after each move.
4. Do not change constants, translation strings, or patch bytes during moves.
5. Compare generated artifacts when an import move touches executable paths.

## Phase 3: decompose the human-test builder

`build_human_test_disc.py` is now large enough that unrelated responsibilities
are difficult to review independently. Split it only after Phase 2 establishes
stable shared namespaces.

Separate at least these concerns:

- authenticated source-set discovery;
- immutable translation profile data;
- text encoding and wrapping;
- row-layout transformations;
- optional title graphics;
- patch planning;
- raw-sector application;
- output manifest generation; and
- post-build verification.

The split should produce identical patch plans for the same authenticated input.
A golden local patch-plan snapshot is preferable to relying only on final image
hashes because it makes accidental scope expansion easier to diagnose.

## Phase 4: formalize schemas and reusable APIs

Once the internal package layout stabilizes:

- version TSV schemas explicitly;
- expose typed records for dialogue and inventory rows;
- centralize TSV read/write rules;
- add machine-readable build-profile metadata;
- expose a dry-run patch-plan command;
- expose a JSON summary mode for automation; and
- define which Python APIs, if any, are supported for third-party callers.

Avoid promising a public Python API before the module boundaries stop moving.
The command line and documented file schemas should remain the durable public
contract in the meantime.

## Phase 5: release engineering

When runtime validation is strong enough for wider distribution of the tools:

- tag toolkit releases separately from translation build-profile names;
- generate release notes from `CHANGELOG.md`;
- build and verify wheel and source distributions in CI;
- publish hashes for release artifacts;
- document supported Python versions per release; and
- retain the no-game-data packaging boundary.

## Explicit non-goals

Modernization alone must not:

- change translation wording;
- reinterpret unknown control bytes;
- promote heuristics into confirmed facts;
- broaden patch ranges without evidence;
- change generated game bytes as a side effect of moving code; or
- make emulator success a substitute for structural verification.
