# Changelog

This file tracks tooling and repository-interface changes. Translation build
profiles and runtime research retain their own evidence and validation notes in
`docs/`.

## Unreleased

### Added

- Installable Python package metadata in `pyproject.toml`.
- Unified `cyber-oedo` command and `python -m cyber_oedo` entry point.
- `cyber-oedo doctor` environment diagnostics.
- Cross-platform GitHub Actions testing on Windows and Linux.
- Source-distribution and wheel builds in CI.
- Installed-wheel smoke tests from outside the source checkout.
- Dependabot configuration for Python and GitHub Actions dependencies.
- Contributor, security, development, release, and modernization documentation.
- Separate issue forms for tooling defects and reverse-engineering evidence.
- Package-surface, packaging-metadata, and command-forwarding regression tests.
- Auditable `auxiliary_rejected.tsv` output for conservatively suppressed
  dialogue-shadow fragments.

### Changed

- CI now runs once per pull-request commit, runs push checks only on `main`, and
  cancels superseded runs on the same ref.
- The README documents the stable package/CLI boundary and distinguishes
  code-path evidence from runtime-confirmed dialogue-control behavior.
- The architecture guide now treats package migration as active transitional
  architecture rather than a hypothetical future conversion.
- Package discovery accepts future `cyber_oedo` subpackages without another
  distribution-layout change.
- Auxiliary-text extraction now rejects only source-guarded, resource-local,
  nearby proper substrings of structured dialogue that terminate into long zero
  fill, while retaining ambiguous candidates for human review.
- The consolidated Tier-A pipeline performs auxiliary shadow filtering inside
  its existing Track 2 mapping, avoiding another full-payload read.

### Compatibility

- Existing root-level script entry points remain supported.
- The legacy three-positional-argument auxiliary extractor invocation remains
  available and performs overlap-only subtraction; source-guarded shadow
  filtering is enabled when the resource map and Track 2 payload are supplied.
- No parser rules, binary formats, patch coordinates, translation text, or game
  bytes are intentionally changed by the tooling-foundation modernization.
