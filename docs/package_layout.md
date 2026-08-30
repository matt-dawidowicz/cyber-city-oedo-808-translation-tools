# Package layout and compatibility shims

Reusable implementation ownership now lives under `cyber_oedo/`.
Historical root modules remain deliberately thin compatibility shims.

## Namespaces

- `cyber_oedo.disc`: disc geometry, CloneCD metadata, Mode 1 integrity, and
  Track 2 extraction.
- `cyber_oedo.text`: dialogue parsing, inventory generation and validation,
  relocation models, and wide-text encoding.
- `cyber_oedo.graphics`: PC Engine tile codecs, title assets, rendering, and
  contact-sheet tooling.
- `cyber_oedo.analysis`: scanners, text-slot analysis, and HuC6280 disassembly.
- `cyber_oedo.experimental`: isolated Stage 1 English-renderer experiments.

`build_human_test_disc.py` remains at the root until its trust-boundary
responsibilities are decomposed separately. That work is intentionally isolated
from this namespace migration.

## Compatibility policy

A historical import such as `import game_layout` resolves through a shim that
re-exports the objects owned by `cyber_oedo.disc.game_layout`. The shim does not
copy constants, classes, or functions; callers receive the implementation
objects themselves.

Historical command invocation also remains supported. For example,
`python extract_dialogue.py ...` delegates to the packaged implementation's
`main()` function. The unified `cyber-oedo` command continues to target the
historical module names, so its behavior does not change during migration.

New implementation code should import from `cyber_oedo.*` directly. Root-level
imports exist for compatibility and should not become new dependency edges.

## Change boundary

This migration changes module ownership only. It does not intentionally change
parser rules, translation wording, schemas, patch coordinates, renderer logic,
source hashes, expected bytes, or generated game data.
