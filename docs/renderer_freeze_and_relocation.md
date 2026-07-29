# Renderer freeze and relocation strategy

## Baseline decision

The stable baseline is commit `f7c0e6e` (`Complete v0.9 opening
localization`). It is the last committed build before the compact-renderer
experiment. It uses fullwidth Shift-JIS text, the System Card's native 16x16
glyph path, same-size replacements, and explicit row reflow for the opening
dossiers and Media Mix pages.

The later experiment is frozen separately:

| Item | Frozen value |
|---|---|
| branch | `agent/compact-english-renderer` |
| archive tag | `archive/compact-renderer-experiment-2026-07-26` |
| commit | `3abaf64` (`Freeze compact renderer experiment`) |
| test snapshot | 56 tests passed |
| translation patches | 428 |
| binary patches | 139 |
| runtime status | incomplete; not a playable baseline |

That commit retains `compact_text.py`, its compiler/runtime code, every English
string added during the experiment, its tests, and its documentation. The
stock-renderer branch does not import or execute any of it. Recover or compare
the source without checking it out:

```powershell
git show 3abaf64:build_human_test_disc.py
git diff f7c0e6e..3abaf64 -- build_human_test_disc.py
```

The freeze preserves translation authorship while preventing experimental
bytes from entering a playable image.

## Playable-build contract

`build_human_test_disc.py` now identifies itself as
`mission0-stock-renderer`.

- `MISSION0_RENDERER_PATCHES` is an explicitly empty tuple.
- No parser, glyph, cursor, punctuation, or code-cave bytes enter
  `HUMAN_TEST_BINARY_PATCHES`.
- English uses fullwidth Shift-JIS through the shipped BIOS font path.
- Ordinary dialogue lines remain within the confirmed 11-cell limit.
- Existing same-size translation, profile row reflow, Media Mix row reflow,
  Mode 1 rebuilding, title opt-out, and whole-image verification remain.

This is a structural contract. A newly generated image still requires emulator
testing before it can be called release-ready.

## Current `KURUZER` evidence

The opening narration is the first record in the named `KURUZER` resource:

| Evidence | Payload coordinate |
|---|---:|
| `KURUZER` header | `0x00175800` (relative sector 747) |
| narration marker | `0x00175828` (`KURUZER + 0x28`) |
| record size | 696 bytes, marker through terminator |
| existing page controls | nine `0x40` bytes |
| next named header | `MAYA01` at `0x00179800` (sector 755) |

The resource therefore spans eight candidate sectors, but that span contains
other dialogue and opaque data. Its tail is not uniform enough to establish
free space. A bounded search also found coincidental 16-bit byte matches, but
no table or runtime reference has been proven to point to the narration
marker.

The record may be inline in a resource command stream. Until tracing proves
otherwise, do not create a `PointerSite` for it and do not activate a
relocation. The machine-readable evidence is
`docs/evidence/kuruzer_relocation_evidence.json`.

## Page-break strategy

`dialogue_relocation.py` provides a stock-renderer compiler with explicit
translator decisions:

1. Author natural English.
2. Split it into pages at sentence or thought boundaries.
3. Give every page explicit lines, each no longer than 11 fullwidth cells.
4. Use at most the runtime-confirmed number of visible lines for that resource.
5. Pad only non-final lines so the stock cursor wraps at a word boundary.
6. Encode each glyph as two-byte Shift-JIS.
7. Insert the already observed `0x40` page command between pages.
8. Keep the `27 28` marker and final `00` terminator.

`PageBreakPlan` validates the exact source record before compiling. It accepts
only page-only source streams. A record containing `0x21`, `0x2F`, `0x5C`, or
another command needs a record-specific control template; those commands must
not be discarded or guessed.

The compiler never removes an existing page break. Additional pages require
`allow_added_page_breaks=True`. That flag records an engineering decision; it
is not runtime proof. Added pages must be tested for window clearing, input
skip, timing, and the transition after the final terminator.

## Pointer-aware relocation strategy

Relocation is safe only when reachability and ownership are both explicit:

1. Identify whether the record is pointer-addressed or inline bytecode.
2. For a pointer-addressed record, map every table entry, alias, and call site.
3. Prove the pointer base and unsigned 16-bit address window.
4. Prove the complete resource load extent.
5. Choose destination bytes already inside that extent so no loader length
   changes are needed.
6. Prove ownership of every destination byte. A name boundary, repeated fill,
   or low entropy is only a candidate.
7. Compile the English record and verify it fits the exact owned area.
8. Guard the original record, every old pointer value, and every destination
   byte.
9. Update all proven pointers while leaving the original record intact.
10. Rebuild affected Mode 1 sectors and compare the complete source/output
    images.

The code enforces this model:

- `PointerSite` stores one exact pointer offset, base, and source target.
- `RelocationArea` stores exact destination bytes and a proven loaded range.
- `DialogueRelocationPlan` rejects an empty pointer list, target mismatch,
  overflow, overlap, out-of-range destination, and insufficient capacity.
- `to_payload_patches()` emits a no-op source guard, every pointer update, and
  one same-size destination-area patch.
- `find_u16_pointer_candidates()` only reports byte matches. Its results are
  never promoted to `PointerSite` automatically.

If tracing proves that a record is inline, this model deliberately refuses to
pretend it has a pointer. The next unit of relocation must then be the owning
script/resource structure, with its entry instruction, offsets, lengths, and
load extent mapped together.

## Activation stop conditions

Do not add a relocation to the playable builder when any of these are true:

- no runtime-proven pointer or resource entry site reaches the source;
- candidate pointer aliases have not been exhaustively mapped;
- the source contains mixed controls without a control template;
- page geometry is inferred from static bytes alone;
- additional `0x40` pages have not been replayed in the active scene;
- destination ownership or loaded extent is uncertain;
- relocation would require an unmapped length or sector-count change;
- the replacement crosses a bank or 16-bit pointer window; or
- the following scene, audio, save, and reload checks have not been run.

## Copy-paste validation

From the toolkit root:

```powershell
$python = "C:\path\to\python.exe"
& $python -m unittest discover -s tests -v
& $python -m py_compile *.py tests\*.py
git diff --check
```

Before an activated relocation, add synthetic unit tests first, then a
source-backed test that verifies:

- the exact source record hash and control list;
- the complete pointer-site list and old pointer bytes;
- resource start/end and pointer-base arithmetic;
- exact destination bytes and capacity;
- compiled page count, line count, and final record size; and
- the exact set of changed payload sectors.

The final gate is a focused emulator replay of the relocated scene followed by
the next scene, audio continuity, save, restart, and reload.
