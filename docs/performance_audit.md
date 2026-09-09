# Performance and architecture audit

This document records the modernization campaign from the restored pre-reset
baseline. It distinguishes measured algorithmic/I/O problems from structural
debt that does not materially slow normal builds.

## Eliminated bottlenecks

### Large-payload analysis

The analyzed Track 2 payload is 84,375,552 bytes. The old analysis commands
frequently copied that entire file into Python heap memory, accumulated complete
report tables in lists, and sometimes opened the payload again for hashing.

The modernized pipeline now:

- uses a read-only memory map for large analysis inputs;
- streams sector, string, dialogue, auxiliary, and resource-tail TSV rows;
- hashes an already mapped payload instead of reopening it;
- computes sector nonzero count, unique-byte count, and entropy from one byte
  frequency table instead of independent scans;
- computes Shift-JIS Unicode shape metrics once per candidate;
- validates translator inventories in a streaming pass rather than retaining
  every row;
- streams inventory summaries and keeps only aggregate counters and canonical
  identifiers;
- memory-maps the experimental reversed-SJIS scanner and streams its report;
- reads only the requested byte range for HuC6280 disassembly.

### Translation inventory construction

The old inventory builder concatenated dialogue and auxiliary dictionaries,
stored hexadecimal offsets as strings, reparsed offsets inside a sort key,
sorted all occurrences, and then built a second complete output list.

The modernized builder uses typed numeric `Occurrence` records internally and
merges the already offset-sorted inputs with `heapq.merge`. The merge is linear
in the number of occurrences. A first sequential pass counts duplicate source
texts; the second sequential pass writes the inventory directly.

### Shift-JIS parsing

Lead-byte, trail-byte, halfwidth-Katakana, token-run, and Unicode-shape logic had
several subtly different implementations. `cyber_oedo.text.sjis` is now the
canonical byte-classification layer for normal and exploratory scanners and the
structured dialogue extractor.

### Raw image build and verification

The old human-test build contained the largest avoidable I/O costs:

- whole-image comparison performed one 2352-byte read per sector from each IMG;
- the output IMG was then read again solely to calculate SHA-256;
- output verification reread an affected raw sector for each patch fragment;
- patch application tested every patch against every affected sector;
- a successfully rebuilt sector immediately performed another full EDC/ECC
  rebuild as an assertion.

The modernized build now:

- indexes patches by affected payload sector before opening the output IMG;
- presents each sector only the patches that can intersect it;
- validates all affected source sectors before writing rebuilt sectors;
- performs one raw-sector rebuild during application;
- rereads each affected output sector once and verifies every replacement slice
  plus Mode 1 integrity during that read;
- compares source and output images in aligned 2048-sector chunks;
- descends to 2352-byte comparisons only inside chunks that differ;
- calculates the output IMG SHA-256 during the same pass as comparison, removing
  a complete additional output-image read.

The exact source-byte guards, same-size patch rules, source hashes, Mode 1
EDC/ECC verification, changed-sector allowlist, and CCD/SUB identity checks are
preserved.

### Command dispatch and compatibility

The unified CLI no longer uses `runpy` while temporarily replacing global
`sys.argv`. Normal pipeline and automation commands accept explicit argument
vectors and are called directly as package APIs. This removes global process
state, repeated module execution as `__main__`, and makes command dispatch safe
to invoke from tests or another Python process.

A small number of unchanged historical diagnostic/experimental commands still
run in an isolated child interpreter. That adds Python process-startup latency,
but these are operator diagnostics rather than hot pipeline stages. Their
historical standalone script interfaces remain intact.

## Complexity changes

| Path | Restored baseline | Modernized path |
| --- | --- | --- |
| Large payload ownership | full Python `bytes` copy | read-only `mmap` |
| Report generation | accumulate then write | stream rows |
| Inventory merge | concatenate + `O(n log n)` sort | `O(n)` sorted merge |
| Patch scheduling | affected sectors x all patches | patch-to-sector index |
| Patch readback | one raw read per fragment | one raw read per sector |
| Whole IMG comparison | 2352-byte reads for every sector | multi-MB aligned chunks |
| Output IMG hash | separate full-file pass | folded into comparison pass |
| HuC6280 range read | `O(file size)` input read | `O(requested length)` read |

## Structural decomposition completed

The active human-test build is no longer orchestrated by the legacy monolithic
engine. Responsibilities now have explicit modules:

- `cyber_oedo.build.source` authenticates source sets;
- `cyber_oedo.disc.patching` schedules and applies guarded sector patches;
- `cyber_oedo.build.image_verify` performs optimized readback and whole-image
  verification;
- `cyber_oedo.build.manifest` serializes build evidence;
- `cyber_oedo.build.pipeline` owns build orchestration;
- `cyber_oedo.build.human_test` is the explicit public compatibility API.

The prior dynamic `globals().update(...)` facade and duplicate private dialogue
and inventory implementation copies have been removed.

## Deliberately retained compatibility debt

`cyber_oedo.build.engine` still contains the historical stock-renderer profile:
hand-audited source strings, English test text, exact offsets, row coordinates,
and patch definitions. Moving thousands of literal profile values to TSV/JSON
would improve editability, but it is not a runtime bottleneck and is high risk
without an authenticated real-disc equivalence check. The active orchestration,
I/O, verification, and manifest code have already been moved out of that module.

A future mechanical profile-data migration should be accepted only if both title
variants produce the identical deterministic patch-plan SHA-256, identical
source/replacement hashes, and identical guarded-sector footprints before and
after the move. It should not be mixed with translation or renderer changes.

Root-level modules also remain installed as thin compatibility shims for old
`python script.py ...` workflows. Canonical normal-pipeline execution goes
through `cyber_oedo.*`; preserving the shims costs little and prevents an
unnecessary breaking release.

## Safety rules retained

1. Preserve exact original-byte guards and authenticated source hashes.
2. Preserve raw Mode 1 EDC/ECC correctness and changed-sector verification.
3. Stream or map large inputs; do not trade correctness for speculative
   micro-optimizations.
4. Use typed numeric models internally and serialize textual offsets only at
   external boundaries.
5. Keep one canonical Shift-JIS byte model.
6. Keep compatibility shims at the outer boundary rather than routing new code
   through them.
7. Keep experimental renderer/relocation work isolated from the stable
   stock-renderer build.
