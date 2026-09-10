# Tier A architecture

Tier A is the host-side reverse-engineering, translation, compilation, and
verification layer. Its job is to make the original game understandable and
reproducibly editable without requiring runtime-engine changes.

## Language policy

Python is the authoritative implementation language for Tier A.

Use Python for:

- binary and resource parsing;
- dialogue/script ASTs;
- translation inventories and logical-text reconstruction;
- structure-specific serializers;
- resource ownership and allocation models;
- deterministic patch planning;
- disc verification and manifest generation;
- SQLite/TSV/JSON analysis outputs; and
- regression and property-style tests.

Rust is optional and must be introduced only for a measured, isolated need.
Suitable examples are a demonstrably dominant CPU-bound scanner, a hardened
standalone public patch applicator, or a binary primitive whose safety or
performance materially benefits from native code. A Rust component must have a
stable Python-facing or file-contract boundary and must not become the only
implementation of a still-evolving reverse-engineered format.

Do not add Rust merely to replace working Python. Profile first.

HuC6280 assembly belongs to Tier B and is not part of this layer.

## Canonical operator pipeline

The normal Tier-A operator path is `cyber-oedo analyze`. It maps Track 2 once
for resource-map discovery, likely Shift-JIS scanning, and structured dialogue
extraction, then emits the same stable TSV contracts used by the individual
forensic commands. Auxiliary-text subtraction, inventory generation, validation,
and the optional SQLite evidence database remain explicit downstream stages.

`scan-track` is broad reconnaissance, not a required translation stage.
Individual commands remain supported when a researcher needs to isolate or
debug one stage. `analyze-text-slots` consumes the canonical resource map rather
than rediscovering resource headers from ASCII scan output.

## Structural rule

Tier A models game structures before editing them. Every parser intended for
insertion work should have a lossless serializer and should satisfy the core
round-trip invariant on authenticated or synthetic source bytes:

```text
serialize(parse(source)) == source
```

A scanner can remain heuristic. A compiler or reinserter cannot.

## Dialogue milestone

The first Tier A implementation replaces the historical "any low byte is one
control, zero always terminates" model with an opcode-aware dialogue parser.
The active `27 28` dialogue interpreter has the following statically established
command shapes:

| Opcode | Operand bytes | Tier A name |
|---:|---:|---|
| `21` | 0 | `wait_state` |
| `2A` | 1 | `command_2a` |
| `2F` | 0 | `timed_wait` |
| `3D` | 2 | `indirect_text` |
| `40` | 0 | `page_break` |
| `5C` | 0 | `wait_input` |
| `7E` | 1 | `command_7e` |
| `00` | n/a | record terminator at dispatch level |

The important distinction is that a zero byte consumed as an operand is data,
not a terminator. In particular, a stream such as `3D 00 06` must consume both
operand bytes before scanning resumes.

`cyber_oedo.script` provides:

- immutable typed text and control nodes;
- exact source offsets for every node;
- strict known-opcode parsing by default;
- an explicit forensic mode for unknown one-byte controls;
- operand-aware audit tags;
- a version-1 compatibility projection for the existing dialogue TSV; and
- marker-through-terminator lossless serialization.

The legacy `extract_dialogue.parse_record()` API now projects from this richer
model so relocation and inventory callers can continue to work while new code
uses the typed parser directly.

## Planned Tier A phases

### A1. Script grammar and exact round trips

- Finish opcode discovery for all reachable dialogue/script commands.
- Add real-disc round-trip coverage against authenticated record samples.
- Introduce versioned structured-command output once semantics require fields
  beyond the current dialogue TSV.
- Reconcile broad Shift-JIS "auxiliary" hits that are actually command-stream
  continuations.

### A2. Complete resource map

- Promote sector-aligned resource-header discovery into a first-class model.
- Record every candidate header, including resources with no extracted text.
- Separate candidate boundaries from proven loader extents.
- Trace the resource registry/loader to establish disc range, load address,
  loaded size, aliases, and ownership evidence.
- Never infer writable free space from fill bytes alone.

### A3. Logical text structures

- Build format-specific models for dialogue, opening dossiers, Media Mix,
  database/news pages, credits, ending narration, debug/omake text, and other
  discovered interpreters.
- Reconstruct logical articles/pages before English reflow instead of treating
  every physical Japanese fragment as an independent translation unit.
- Preserve canonical translation IDs while allowing occurrence-specific context.

### A4. Compiler and allocator

- Compile translated logical structures back into exact game bytecode.
- Preserve command order and operands unless a reviewed transformation says
  otherwise.
- Model resource-local capacity and ownership explicitly.
- Produce deterministic allocation/overflow plans rather than searching for
  "empty-looking" bytes during a build.

### A5. Verification database and release pipeline

- Generate a queryable SQLite analysis database in addition to stable TSV/JSON
  interchange files.
- Track source hashes, parser version, resource ownership, runtime coverage,
  translation status, compiled size, allocation decision, changed sectors, and
  validation evidence.
- Keep the existing authenticated CloneCD build boundary: exact source guards,
  EDC/ECC rebuilding, whole-image comparison, and byte-identical CCD/SUB files.

## Rust admission criteria

A Rust component is justified only when all of the following are true:

1. the format or algorithm is already stable enough to define a narrow contract;
2. profiling identifies a material bottleneck or native safety benefit;
3. the Python reference behavior is covered by tests;
4. the native component can be replaced by the Python implementation for
   debugging or verification where practical; and
5. introducing Rust does not make normal translation/research work depend on a
   complicated native build environment.

Until those conditions are met, Python remains the correct implementation.
