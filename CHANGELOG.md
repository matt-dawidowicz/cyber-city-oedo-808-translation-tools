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
- Wheel-build validation in CI.
- Dependabot configuration for Python and GitHub Actions dependencies.
- Contributor, security, development, and modernization documentation.
- Package-surface regression tests.

### Compatibility

- Existing root-level script entry points remain supported.
- No parser rules, binary formats, patch coordinates, translation text, or game
  bytes are intentionally changed by the tooling-foundation modernization.
