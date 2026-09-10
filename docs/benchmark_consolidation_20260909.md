# Benchmark-driven architecture consolidation — 2026-09-09

This report records the architecture/performance pass based on `main` at
`6f76fa61ba26085670315ed655dc5dc4d3e6da0c`. The pass deliberately treats
wall time, memory use, and exact output identity as the optimization criteria;
loop count and pass count are not performance metrics.

## Benchmark source and environment

The full authenticated Track-2 payload was used wherever a real payload was
required:

- bytes: `84,375,552`;
- SHA-256: `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`.

Representative local measurements in this report used CPython 3.13.5,
NumPy 2.3.5, and Numba 0.65.1 on the same Linux runner. Benchmark workers run
in separate processes so peak RSS is meaningful. Warm cases explicitly execute
the relevant Numba kernel before timing. Cold cases use an empty Numba cache.
Median and median absolute deviation (MAD) are reported rather than best-case
numbers.

The benchmark programs are:

```text
benchmarks/bench_scans.py
benchmarks/bench_pipeline.py
benchmarks/bench_build.py
```

They authenticate the payload before timing and record exact row counts and
output hashes. The scan and pipeline harnesses also assert equivalence between
behaviorally equivalent implementations.

## Scan benchmarks

The unchanged sector/broad/likely kernels remain effectively neutral. Small
movement in either direction is below the threshold for an optimization claim.
The significant measured change is native rejection of structurally valid but
strictly undecodable broad Shift-JIS candidates before Python decode/formatting.

| Case | Before median | Before MAD | After median | After MAD | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| sector metrics, warm | 221.34 ms | 0.32 ms | 237.66 ms | 1.52 ms | no claim; same kernel/output |
| structural broad SJIS, warm | 1172.32 ms | 2.13 ms | 1176.96 ms | 7.90 ms | no claim; same kernel/output |
| likely SJIS, warm | 1264.47 ms | 0.73 ms | 1286.48 ms | 4.50 ms | no claim; same output |
| decoded broad SJIS | 3133.48 ms | 10.86 ms | 2850.59 ms | 118.41 ms | **282.88 ms / 9.0% faster** |

Decoded broad-SJIS equivalence:

- rows before: `886,104`;
- rows after: `886,104`;
- output SHA-256 before/after:
  `25037e66a55767bdf38547e4feb702f88e7c733a6b34bbc7052dc941a5085446`;
- representative peak RSS before: about `276.5 MiB`;
- representative peak RSS after: about `272.4 MiB`.

The decoded-path improvement is just under the nominal 10% hot-path threshold,
but the absolute saving is roughly 0.28 seconds per complete broad decode on an
84 MiB payload and does not increase warm RSS. It is therefore retained.

### Numba cold versus warm

The benchmark harness measures cold compilation separately rather than mixing it
into steady-state numbers.

| Kernel | Cold | Warm median | Cold overhead |
| --- | ---: | ---: | ---: |
| sector metrics | 1048.48 ms | 237.66 ms | about 811 ms |
| decoded broad native filter + decode | 3504.35 ms | 2850.59 ms | about 654 ms |

Cold numbers include the first JIT invocation for that kernel in an empty Numba
cache. They are not presented as steady-state scan throughput.

## Tier-A pipeline benchmarks

The new `cyber-oedo analyze` orchestration maps Track 2 once for the three
payload-dependent stages and keeps the established stable TSV contracts. It is
an architectural consolidation, not a speed optimization.

| Path | Median | MAD | Peak RSS | Aggregate rows | Aggregate hash |
| --- | ---: | ---: | ---: | ---: | --- |
| baseline individual commands | 2094.82 ms | 2.58 ms | 257.1 MiB | 13,568 | `faa919c85a9fb723a43776a067c06298f837751437fede291dbb7536e7547cca` |
| current individual commands | 2132.88 ms | 6.03 ms | 256.9 MiB | 13,568 | same |
| current in-process orchestrator | 2146.76 ms | 14.22 ms | 256.9 MiB | 13,568 | same |

The orchestrator measured about 2.5% slower than the baseline in this run and
about 0.7% slower than the current individual-command path. That difference is
small relative to the architectural benefit and is explicitly **not** claimed as
an optimization. The reason to retain the orchestrator is one canonical Tier-A
flow, one payload map for payload-dependent stages, less duplicated CLI/process
plumbing, and stable forensic commands remaining available independently.

The current orchestrated artifacts match the baseline byte-for-byte:

| Artifact | Rows | SHA-256 |
| --- | ---: | --- |
| `resource_map.tsv` | 724 | `4b8c0f178b652adace60e1ad16ff85cda2a8245e76106e9a0d1b732228f47155` |
| `likely_sjis.tsv` | 2,450 | `4b8c73a447fb5bede307cd78c60581ae65231c47fe87f17cd087bd8223cd8d2c` |
| `dialogue.tsv` | 3,815 | `7cb570ce6f431b305fe9f858890e6020b96291f9f003c5d1ce629190d8cabbdd` |
| `auxiliary.tsv` | 1,382 | `15f9a4d7b1b1d080f1b55786f3d6ade70f79a131a7ac2a6bb15498cc5d576c75` |
| `translation_inventory.tsv` | 5,197 | `c58d76693f24053eeecfd34c5633d3abd71bee3d103f29635e388ad670e87d06` |

## Build benchmarks

Planning and mutation were benchmarked separately. The build refactor is
primarily structural: one prepared recipe now feeds planning, manifest
serialization, and execution while independent verification remains separate.

| Case | Before median | Before MAD | After median | After MAD | Identity |
| --- | ---: | ---: | ---: | ---: | --- |
| hash-only plan | 3.59 ms | 0.41 ms | 3.57 ms | 0.07 ms | unchanged |
| guarded 21-sector mutation | 32.25 ms | 5.86 ms | 26.19 ms | 1.36 ms | unchanged |

The patch microbenchmark happened to measure faster after consolidation, but the
baseline variance is high enough that no speedup claim is attached to it. Peak
RSS is effectively unchanged at about `107.4 MiB`.

The original-title plan SHA-256 remains:

`7372c5ee7dc54d30bf2545a5ca9eaa8ad9231e03ecf2cb3faaf723d0cbad3de5`

The clean-title plan SHA-256 remains:

`3255c65bbd3dd8ec37daf05d315894ad3a1b7af5815228bcf9034b046367b4bb`

The synthetic patched-sector output SHA-256 remains:

`c3ee3d8578fa545b558cff84029230630959979578814f4b35203445e49757a7`

## Architectural consolidation

### One patch mutation implementation

`cyber_oedo.disc.patching.apply_payload_patches()` is now the only payload
patch-mutation implementation. `cyber_oedo.disc.cdrom_mode1` owns Mode-1
structure validation, EDC/ECC primitives, payload reads, and sector rebuilding;
it no longer contains a second patch scheduler/orchestrator.

An architecture regression test scans the package AST and requires the single
implementation to remain in `disc/patching.py`.

### Prepared build recipe

`cyber_oedo.build.recipe` introduces typed `BuildRecipe`, `PreparedPatch`, and
`BuildResult` objects. One prepared recipe feeds:

- source-independent hash-only planning;
- manifest row generation; and
- actual payload mutation once source-dependent title bytes are materialized.

`cyber_oedo.build.verification` remains independent and still compares the plan
against the separately maintained reviewed profile footprint. Output readback,
raw-image comparison, source authentication, Mode-1 EDC/ECC checks, and CCD/SUB
identity checks remain separate trust boundaries.

The build CLI now prints directly from `BuildResult`; it does not write a JSON
manifest and immediately parse that file again merely to recover values already
known in memory.

### Canonical resources and tabular boundaries

`analyze-text-slots` now consumes the canonical Tier-A resource map and
`cyber_oedo.resources.ResourceHeader` instead of deriving a second resource-name
model from `ascii_strings.tsv`.

Small repeated UTF-8-SIG TSV `DictReader`/`DictWriter` setup is centralized in
`cyber_oedo.tabular`. The module is intentionally narrow; no catch-all
`utils.py` was introduced.

### Canonical hashing and mapping

Simple file/buffer SHA-256 operations and memory mapping remain in
`cyber_oedo.io`. Analysis/runtime modules no longer carry private one-off
SHA-256 helpers. Streaming digests that are intrinsically part of copy/image
comparison loops remain local to those streaming operations.

### Pipeline status of `scan-track`

`scan-track` is retained as optional diagnostics for broad ASCII/Shift-JIS and
sector reconnaissance. The normal Tier-A translation path is now approximately:

```text
extract Track 2
  -> resource map
  -> likely Shift-JIS
  -> structured dialogue
  -> auxiliary text subtraction
  -> translation inventory
  -> validation / analysis database
```

`cyber-oedo analyze` performs that flow in process; the individual commands stay
available for forensic/debug use.

## Rejected or deliberately unclaimed optimizations

- A one-pass Numba typed-list scanner remains rejected; earlier measurements
  showed it substantially slower than the two-pass fixed-array strategy.
- Loop/pass count is not used as a proxy for performance.
- Rare image-diff-sector vectorization remains rejected because the measured
  end-to-end gain was trivial relative to complexity.
- The Tier-A orchestrator is retained despite neutral/slightly worse wall time
  because the architecture is materially simpler and output identity is exact.
- The build microbenchmark improvement is not advertised as a speedup because
  baseline MAD is too large for a strong conclusion.

## Integrity boundary

This pass does not introduce translation/runtime mutation behavior. It preserves:

1. authenticated source-byte and source-file guards;
2. immutable source media and copy-before-mutation behavior;
3. CloneCD geometry;
4. raw Mode-1 EDC/ECC reconstruction and verification;
5. deterministic patch-plan identities and reviewed sector footprints;
6. independent final readback/image verification;
7. Tier-A/Tier-B evidence semantics; and
8. the prohibition on a global escape marker.
