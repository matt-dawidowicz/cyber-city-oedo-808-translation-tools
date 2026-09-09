# Performance and architecture audit

This document tracks the modernization campaign from the restored pre-reset baseline.

## Confirmed hotspots

- Analysis commands copied the entire 84,375,552-byte Track 2 payload into Python heap memory for each pass.
- `scan_track` buffered complete TSV reports in lists and then reread the payload only to hash it.
- Sector reconnaissance performed separate Python passes for nonzero counts, unique-byte counts, and entropy.
- `scan_likely_sjis` computed Unicode shape metrics twice for every retained candidate and buffered every result row.
- Structured dialogue extraction buffered all records before writing them.
- Auxiliary extraction buffered all output rows and materialized the complete dialogue TSV before range merging.
- Translation inventory generation concatenated both TSVs into dictionaries, reparsed hexadecimal offsets during sort, sorted all occurrences, then built a second complete output list.
- Shift-JIS lead/trail classification existed in multiple independent implementations.
- Unified CLI dispatch used `runpy` plus temporary global `sys.argv` mutation.
- Package facades used dynamic `globals().update(...)`, obscuring API ownership and static analysis.
- The human-test builder scans the full raw IMG sector-by-sector with 2352-byte reads when comparing source and output.
- The human-test builder rereads the complete output IMG after comparison solely to compute SHA-256.
- Output patch verification rereads a raw sector once per patch fragment rather than once per affected sector.
- Raw Mode 1 patch application tests every patch against every affected sector instead of indexing patches by sector.
- Successful sector rebuilding immediately recomputes EDC/ECC a second time as an assertion.
- The legacy build engine combines profile data, translations, layout definitions, encoding, build orchestration, verification, title generation hooks, manifests, and CLI behavior in one large module.
- Translation strings and layout coordinates are executable Python data rather than a clearly separated profile/corpus boundary.
- Root compatibility modules are still installed as first-class modules and some package code imports through those shims.

## Modernization rules

1. Preserve exact binary guards, source authentication, EDC/ECC correctness, and changed-sector verification.
2. Optimize whole-image I/O before micro-optimizing 84 MB analysis passes.
3. Stream or memory-map large read-only inputs and stream generated reports.
4. Use typed numeric models internally; serialize hexadecimal strings and TSV dictionaries only at boundaries.
5. Keep one canonical Shift-JIS byte model.
6. Keep compatibility shims only at the outermost API boundary; canonical package modules must import package modules directly.
7. Move toward explicit callable command entry points instead of global `sys.argv` mutation.
8. Keep experimental renderer/relocation work isolated from the stable stock-renderer build.
