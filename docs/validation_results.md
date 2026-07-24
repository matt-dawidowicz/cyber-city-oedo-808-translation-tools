# Validation results

Validation date: 2026-07-24

These results describe the documented toolkit in this directory. They separate
code/tool validation from emulator or hardware validation.

## Source and extraction

`extract_track2_mode1.py` was run against the supplied IMG with its title-
specific defaults:

```text
bytes=84375552
sectors=41199
sha256=0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223
```

The result matches the previously extracted payload byte-for-byte by hash.

This validates:

- the selected raw-sector range;
- sync/mode checks;
- user-data slicing; and
- deterministic output identity.

It does not validate source EDC/ECC mathematically or boot the result.

## Synthetic tests

Command:

```powershell
python -m unittest discover -s .\tests -v
```

Result:

```text
Ran 13 tests
OK
```

Covered behavior:

- half-open mission bank boundaries;
- payload/LBA coordinate helpers;
- Shift-JIS plus opaque control tokenization;
- unterminated-record rejection;
- invalid dialogue-parser bound rejection;
- overlap/adjacency interval merging;
- resource-name versus fill filtering;
- PCE 4bpp plane order; and
- structurally valid Mode 1 user-data extraction;
- docstrings on every module, class, and function;
- PEP 257 summary shape;
- PEP 8's 79-character Python line limit; and
- conventional explanatory-comment prefixes.

## Script loading and CLI documentation

Every Python source file, including the tests, passed `py_compile`.

Every command-line script returned success for `--help`:

- `analyze_text_slots.py`
- `build_translation_inventory.py`
- `extract_auxiliary_text.py`
- `extract_dialogue.py`
- `extract_track2_mode1.py`
- `make_contact_sheet.py`
- `render_pce_tiles.py`
- `scan_likely_sjis.py`
- `scan_reversed_sjis.py`
- `scan_track.py`
- `validate_translation_inventory.py`

The two PNG tools were also exercised against the real payload, including a
contact-sheet output located inside its input directory.

## Dialogue regeneration

The documented `extract_dialogue.py` reproduced:

```text
records=3799
unique_tagged_texts=2429
sjis_characters=92987
likely_text=3721
review=78
MISSION_0=558
MISSION_1=576
MISSION_2=516
MISSION_3=420
MISSION_4=322
MISSION_5=340
MISSION_6=320
MISSION_7=235
MISSION_8=512
ENDING=0
```

The per-bank counts above include both `likely_text` and `review`.

## Broad-scan baseline difference

A clean rerun of the documented broad Shift-JIS scanner produced 2,464
candidates. The older saved `scan/likely_shift_jis.tsv` contains 2,180.

Comparison shows:

- every old broad-scan offset is still present;
- 284 candidates are newly present;
- all 284 lie in the `0x02xxxxxx` payload-offset region;
- 164 of them overlap structured dialogue and are removed by the auxiliary
  subtraction stage; and
- 120 remain as additional auxiliary candidates.

This pattern indicates that the older saved broad-scan artifact omitted part of
one payload region; it is not a behavior change caused by the documented
plausibility thresholds. The clean rerun produced:

```text
auxiliary occurrences=1445
auxiliary unique texts=702
combined occurrences=5244
combined canonical texts=3058
combined review occurrences=244
```

The previously published translator inventory remains a valid 5,124-row
baseline and passes the new structural validator with zero errors. It was not
silently overwritten during this documentation pass. Before translation work
begins, choose one baseline explicitly:

- preserve the 5,124-row inventory for continuity; or
- review the 120 additional auxiliary candidates and promote the 5,244-row
  clean regeneration.

The main structured dialogue inventory is unaffected.

## Inventory validation

Older saved inventory:

```text
rows=5124
canonical_ids=3026
warnings=0
errors=0
```

Clean regeneration:

```text
rows=5244
canonical_ids=3058
warnings=0
errors=0
```

Both currently have blank translation columns.

## Resource-region analysis

The header-bounded analyzer produced:

```text
resource_headers=443
text_regions=364
unassigned_records=0
bounded_text_regions=349
wide_header_gaps=15
records_crossing_regions=0
likely_padded_tails=48
```

The 15 gaps above 64 sectors are explicitly labeled `wide_header_gap` and
cannot produce a positive padding candidate by default. This prevents a missing
intermediate header from being presented as confident relocation space.

No dialogue record crossed its assigned candidate region boundary in this run.

## Not validated

- emulator boot;
- runtime control semantics;
- player-visible coverage;
- exact resource pointers/lengths;
- English glyph rendering;
- payload reinsertion;
- EDC/ECC rebuilding;
- CloneCD track/subchannel preservation after patching;
- full-game playthrough.

Those remain required milestones, not implied successes.
