# Versioned external contracts

The toolkit now distinguishes durable automation contracts from internal Python
implementation details.

## Stability boundary

The supported external surface is:

- documented `cyber-oedo` command names and argument behavior;
- versioned TSV schemas described by `cyber-oedo describe-contracts`;
- versioned JSON emitted by automation commands; and
- documented build-manifest fields.

Python module paths under `cyber_oedo.*` remain implementation details unless a
future release explicitly promotes a Python API. Refactors may move Python
symbols while compatibility shims preserve documented commands and file data.

## Current schema versions

All current contracts begin at version 1:

- `cyber-oedo.dialogue-tsv/v1`;
- `cyber-oedo.auxiliary-text-tsv/v1`;
- `cyber-oedo.translation-inventory-tsv/v1`;
- `cyber-oedo.human-test-build-plan-json/v1`;
- `cyber-oedo.human-test-build-manifest-json/v1`; and
- `cyber-oedo.translation-inventory-summary-json/v1`.

The translator inventory's only human-editable fields remain
`english_translation` and `translator_notes`.

## Compatibility rules

Additive informational TSV columns may remain readable by a version-1 consumer
when every required version-1 field is still present. Removing, renaming, or
changing the meaning of a required field requires a new schema version.

A schema migration must write a new artifact or explicitly migrate to a new
version. It must not silently overwrite a translator's master inventory.

## Automation commands

`cyber-oedo describe-contracts` prints the complete contract catalog as JSON.

`cyber-oedo plan-human-test --title-screen clean` emits the complete hash-only
patch plan without opening a source disc. The plan includes a canonical SHA-256
identity, profile metadata, patch categories, guarded offsets, source hashes,
replacement hashes, and the reviewed sector footprint. It never writes a disc
image and never embeds copyrighted expected bytes.

`cyber-oedo inventory-summary translation_inventory.tsv` validates the required
version-1 header and emits stable JSON counts for rows, canonical IDs,
translations, blanks, and quality labels.
