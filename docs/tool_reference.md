# Tool reference

The supported operator surface is the installed `cyber-oedo` command (or
`python -m cyber_oedo`). Historical root-level Python wrappers and the failed
Stage-1/reversed-SJIS commands are retired.

## Pipeline commands

| Command | Canonical module | Purpose |
|---|---|---|
| `extract-track2-mode1` | `cyber_oedo.disc.extract_track2_mode1` | Extract 2048-byte Mode 1 Track 2 payload bytes from the raw IMG. |
| `analyze` | `cyber_oedo.analysis.pipeline` | Run the consolidated Tier-A translation pipeline in process. |
| `build-resource-map` | `cyber_oedo.analysis.build_resource_map` | Build sector-aligned candidate-resource evidence. |
| `scan-likely-sjis` | `cyber_oedo.analysis.scan_likely_sjis` | Find likely natural-language Shift-JIS runs. |
| `extract-dialogue` | `cyber_oedo.text.extract_dialogue` | Extract typed dialogue records. |
| `extract-auxiliary-text` | `cyber_oedo.text.extract_auxiliary_text` | Remove dialogue-overlapping runs from broad text candidates. |
| `build-translation-inventory` | `cyber_oedo.text.build_translation_inventory` | Produce occurrence-level translator TSV data. |
| `validate-translation-inventory` | `cyber_oedo.text.validate_translation_inventory` | Validate generated or translator-edited inventory data. |
| `analyze-text-slots` | `cyber_oedo.analysis.analyze_text_slots` | Measure candidate resource tails without claiming ownership. |
| `build-human-test-disc` | `cyber_oedo.build.human_test` | Build the authenticated stock-renderer vertical slice. |

Typical analysis flow:

```bash
cyber-oedo extract-track2-mode1 source.img track02_mode1_2048.bin
cyber-oedo analyze track02_mode1_2048.bin --output-dir analysis
```

The individual Tier-A commands remain supported when a researcher needs to
inspect or rerun one stage. `analyze-text-slots` now consumes the canonical
`resource_map.tsv` rather than rediscovering resource headers from an ASCII
scan.

All post-extraction offsets are 2048-byte Track 2 payload coordinates unless a
command explicitly documents another coordinate system.

## Automation commands

| Command | Purpose |
|---|---|
| `build-analysis-db` | Build the local SQLite evidence database. |
| `describe-contracts` | Print versioned generated-data contracts. |
| `plan-human-test` | Emit a deterministic no-disc hash-only patch plan. |
| `inventory-summary` | Produce a stable JSON inventory summary. |

Use `plan-human-test` before authenticated build work when reviewing a
supposedly behavior-preserving refactor. Patch-plan identity and guarded-sector
footprint are part of the build contract.

## Runtime and diagnostic commands

| Command | Purpose |
|---|---|
| `scan-track` | Optional broad ASCII/Shift-JIS/sector reconnaissance. |
| `disassemble-huc6280` | Diagnostic linear HuC6280 disassembly at caller-proven coordinates. |
| `prove-dialogue-runtime` | Validate source-guarded Tier-B interpreter/table evidence. |
| `prove-live-dialogue-snapshot` | Validate a bank-aware frozen Mission 0 debugger snapshot. |
| `clonecd-cue` | Create a non-destructive CUE view of a CloneCD set. |
| `render-pce-tiles` | Render raw PCE 4bpp tiles for inspection. |
| `make-contact-sheet` | Combine diagnostic PNG renders. |
| `title-screen` | Generate or preview the optional clean title asset. |

Runtime proof must retain enough bank state to disambiguate HuC6280 overlays.
A logical CPU address alone is not a stable file/resource identity.

## Authenticated human-test build

```bash
cyber-oedo build-human-test-disc source.ccd output-directory
```

Use `--title-screen original` to omit the optional clean title/palette patches.

The build path is decomposed as follows:

- `cyber_oedo.build.profiles.*` owns immutable vertical-slice translation and
  layout data;
- `cyber_oedo.build.plan` owns deterministic source-independent planning;
- `cyber_oedo.build.source` owns source authentication/copy isolation;
- `cyber_oedo.disc.patching` owns guarded Mode 1 payload mutation and EDC/ECC
  rebuilding;
- `cyber_oedo.build.pipeline` orchestrates the build;
- `cyber_oedo.build.manifest` records reviewed output evidence; and
- `cyber_oedo.build.image_verify` performs final image/readback checks.

The authenticated source media is never modified in place.

## Dialogue and relocation APIs

Dialogue is not plain null-terminated text. The maintained parser models command
operand widths explicitly; in particular an operand byte `00` must not be
mistaken for a record terminator.

Stock-renderer presentation lives in `cyber_oedo.text.layout`:

- `PageGeometry`
- `DialoguePage`
- `PageBreakPlan`
- `wrap_dialogue_page`
- `ascii_to_fullwidth_sjis`

Pointer/storage relocation lives separately in `cyber_oedo.text.relocation`:

- `PointerSite`
- `RelocationArea`
- `DialogueRelocationPlan`
- `find_u16_pointer_candidates`

Candidate pointer matches are discovery evidence only. A real relocation also
requires proven reachability, owned destination bytes, source identity guards,
capacity, and non-overlap.

There is no compatibility `cyber_oedo.text.dialogue_relocation` facade.

## Build-profile APIs

The former `cyber_oedo.build.engine` monolith is retired. Use the decomposed
modules directly:

- `cyber_oedo.build.profiles.models`
- `cyber_oedo.build.profiles.startup`
- `cyber_oedo.build.profiles.dossiers`
- `cyber_oedo.build.profiles.media_mix`
- `cyber_oedo.build.profiles.mission0_stock`

The aggregate stock vertical-slice profile is `mission0_stock`; binary I/O and
verification do not belong in that module.

## Graphics APIs

`cyber_oedo.graphics.pce_graphics` provides the raw 8x8 4bpp tile codec.
`cyber_oedo.graphics.title_screen` produces the optional deterministic title
asset/palette. Diagnostic renderers do not own disc mutation.

## Reverse-engineering authority levels

Tool output must be interpreted according to the tier that produced it:

- **Tier A:** authenticated structure, record grammar, candidate resources,
  inventories, exact source coordinates;
- **Tier B:** runtime reachability, overlays/MPRs, state, loaders, pointers,
  renderer/font/VDC behavior, resource lifetime/ownership;
- **Tier C:** active relocation or renderer/storage mutation after the relevant
  Tier-B contracts are proven.

A scanned string is not automatically live text; repeated fill is not free
space; a bootable patch is not sufficient proof of safety.

See `docs/game_architecture_and_translation_strategy.md` for the complete
rationale and the translation policy relative to the OVA.
