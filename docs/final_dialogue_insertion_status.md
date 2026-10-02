# Final dialogue insertion status

This document tracks the path from the reviewed 2026-09-24 localization master
to binary dialogue patches.

## Canonical editorial inputs

- Final workbook SHA-256:
  `6701f387ff62ac365aab9d902945ec0d90661c7e91e4baa713fa120cd2d8c95a`
- Deterministic dialogue-only TSV SHA-256:
  `44ea963798e953a289e6614820579b6484dc7183af43ba031ecef105c27fb502`
- Authenticated Track-2 payload SHA-256:
  `0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223`

The exporter intentionally keeps only `Spoken dialogue` and
`Narration / description` rows. Other text families remain on their dedicated
UI/information/ending paths.

## Current audit

The final master contains 2,237 spoken/narration rows.

| Bank | Total | In-place packed | Relocation required | Mapping required |
|---|---:|---:|---:|---:|
| Mission 0 | 433 | 85 | 214 | 134 |
| Mission 1 | 362 | 73 | 195 | 94 |
| Mission 2 | 344 | 86 | 174 | 84 |
| Mission 3 | 248 | 50 | 98 | 100 |
| Mission 4 | 195 | 34 | 84 | 77 |
| Mission 5 | 195 | 41 | 99 | 55 |
| Mission 6 | 207 | 19 | 92 | 96 |
| Mission 7 | 137 | 12 | 74 | 51 |
| Mission 8 | 116 | 11 | 33 | 72 |
| **Total** | **2,237** | **411** | **1,063** | **763** |

`In-place packed` means all of the following are true:

1. the workbook offset points to a real `27 28` dialogue marker;
2. the workbook Japanese text exactly matches the authenticated bytes after
   that marker;
3. the final English is representable by the packed-English repertoire; and
4. the packed bytes fit the owned Japanese visible span.

`Relocation required` means the binary mapping is exact but the reviewed English
is larger than the existing visible span. The builder must not shorten or
truncate those lines merely to make them fit.

`Mapping required` means the workbook row is not a one-to-one contiguous
visible span immediately after its marker. Typical causes include split records,
embedded controls, auxiliary extraction, or context rows reconstructed from more
than one stored fragment. These rows require record-aware mapping before patching.

## Implemented path

1. `cyber-oedo export-final-dialogue` authenticates the reviewed workbook and
   emits the deterministic TSV.
2. `final_dialogue_insertion.py` source-checks every row and classifies it.
3. `cyber-oedo build-packed-dialogue-test`:
   - authenticates the original CloneCD set;
   - rebuilds the final pair dictionary from the full reviewed dialogue master;
   - rasterizes the user-supplied 8x16 font;
   - installs the Mission 0 packed-English runtime;
   - inserts every currently authenticated Mission 0 row that fits in place;
   - rebuilds Mode-1 EDC/ECC;
   - emits a build manifest and Mission 0 relocation queue.

The packed test profile is deliberately separate from the older stock-renderer
human-test build.

## Immediate Mission 0 result

The first real build target contains **85 final Mission 0 spoken/narration
rows**, plus the packed-English renderer. Those rows need no pointer changes.

The remaining Mission 0 work is:

- 214 mapped rows requiring owned growth/relocation;
- 134 rows requiring record/control-aware binary mapping;
- renderer runtime certification with the final dictionary/atlas rather than the
  single-line bartender proof;
- then full Mission 0 playthrough and save/load QA.

## Scaling to Missions 1-8

Do not insert later-bank private tokens until the font hook/runtime is resident
and source-guarded in that overlay. The insertion planner may classify later
rows now, but build activation is bank-gated.

For each later bank:

1. map/certify the common font hook and runtime storage;
2. enable its already-fitting rows;
3. solve mapped growth through owned relocation;
4. resolve the mapping-required rows;
5. play the mission and verify reveal-order continuity against
   `story_and_continuity.md`.
