# Versioned external contracts

The toolkit versions generated data formats that may be consumed by translators
or automation. Python module paths remain implementation details.

## Current contracts

The restart baseline exposes four version-1 contracts:

- `cyber-oedo.dialogue-tsv/v1`
- `cyber-oedo.auxiliary-text-tsv/v1`
- `cyber-oedo.translation-inventory-tsv/v1`
- `cyber-oedo.translation-inventory-summary-json/v1`

The translation inventory's human-editable fields are
`english_translation` and `translator_notes`. Generated identity, source,
coordinate, and control fields should be regenerated rather than hand-edited.

`cyber-oedo describe-contracts` prints the current catalog as JSON.
`cyber-oedo inventory-summary` validates the inventory header and prints stable
summary counts.

## Removed contracts

The old human-test build-plan and build-manifest schemas described an abandoned
prototype patch pipeline. They are not part of the restart baseline. Their
history is available through Git if it becomes useful when designing a new
patch architecture.

## Compatibility rule

Adding optional informational fields may be compatible with a version-1 reader
when all required fields retain their meanings. Removing, renaming, or changing
the semantics of a required field requires a new schema version.

A schema migration must never silently overwrite a translator's master
inventory.
