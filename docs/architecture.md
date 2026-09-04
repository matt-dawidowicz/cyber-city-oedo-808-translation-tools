# Architecture

## Goal

The restart baseline separates durable reverse-engineering primitives from
translation implementations that are expected to change as runtime behavior is
proven.

## Canonical package

All maintained Python code lives under `cyber_oedo`.

- `disc` owns CloneCD metadata, Mode 1 sector logic, disc constants, and payload
  extraction.
- `analysis` owns broad structural scans, resource-tail heuristics, and HuC6280
  diagnostic disassembly.
- `text` owns structured dialogue extraction, auxiliary-text subtraction,
  translation-inventory generation, and inventory validation.
- `graphics` owns generic PC Engine 4bpp tile codecs and diagnostic rendering.
- `contracts` owns versioned schemas for generated text and automation data.
- `commands` owns small machine-readable operator commands.

The repository root no longer mirrors these modules with compatibility scripts.
Internal imports must use package-qualified paths.

## Command surface

`cyber_oedo.cli` dispatches the installed `cyber-oedo` command and
`python -m cyber_oedo`. Command metadata lives in `cyber_oedo.registry`.
Commands execute package modules directly; no legacy root module is part of the
runtime path.

## Research versus patching

The current active tree stops at analysis and inventory production. It does not
contain the previous authenticated playable-build profile, title replacement,
wide-text engine experiment, or Stage 1 runtime patch.

This is an architectural boundary, not a claim that patching is impossible. A
new patch pipeline should be introduced only after the renderer, control bytes,
resource access paths, and relocation ownership required by that design are
supported by reproducible evidence.

## External data contracts

Generated TSV and summary formats are described by `cyber_oedo.contracts`.
Those contracts are more stable than internal Python module organization. See
`contracts.md` for the current schema set.

## Evidence

Compact evidence artifacts that would prevent repeated investigation belong in
`docs/evidence/`. They should distinguish observations from conclusions and
should not contain redistributable game data. Negative results are useful when
they close off an unsafe assumption.

## Tests

Tests use synthetic bytes and temporary files. They cover hardware codecs,
layout math, parser behavior, contract schemas, and package/CLI integrity
without requiring the original disc or a BIOS.
