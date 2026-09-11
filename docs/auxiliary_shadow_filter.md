# Auxiliary dialogue-shadow filtering

## Problem

The broad Shift-JIS scanner is intentionally permissive: it discovers plausible
Japanese runs anywhere in the Track 2 payload. Structured dialogue is extracted
separately from the confirmed `27 28 ... 00` record format.

Historically, `extract_auxiliary_text.py` removed broad-scan candidates only when
their byte ranges overlapped a structured dialogue record. That allowed short
residual copies of dialogue text elsewhere in the same resource to survive as
translator-facing auxiliary rows. Mission 0 exposed three examples, including
truncated suffixes and prefixes that ended in large zero-filled regions.

## Conservative rejection rule

The canonical Tier-A pipeline now rejects a broad-scan candidate as a
`nearby_dialogue_fragment` only when **all** of the following are true:

1. the candidate lies outside every structured dialogue byte range;
2. the candidate and a structured dialogue record are wholly contained in the
   same candidate resource region;
3. the candidate is not an exact duplicate of the dialogue record's visible
   text;
4. the candidate's exact Shift-JIS bytes occur inside one contiguous dialogue
   text run, never across a control opcode;
5. the candidate is within one 2048-byte payload sector of that dialogue
   record; and
6. the candidate terminates into at least 32 zero bytes, optionally after one
   stranded Shift-JIS lead byte.

The zero-tail requirement is important. The current game contains legitimate
nearby auxiliary labels whose text also appears inside dialogue. Those labels
are followed by other structured data after only a few zero bytes and therefore
remain in the inventory.

## Source guards

When the canonical pipeline runs the shadow filter, both inputs are checked
against the same read-only Track 2 mapping:

- every candidate-resource header must match the payload at its reported start;
- every `dialogue.tsv` `raw_hex` range must match the payload exactly;
- every broad-scan candidate must re-encode to the exact bytes at its reported
  offset; and
- dialogue and broad-scan rows must preserve monotonic offset ordering.

This prevents stale or mixed analysis artifacts from silently influencing the
filter.

## Audit artifact

`auxiliary_rejected.tsv` records each newly suppressed shadow candidate with:

- its original auxiliary coordinates and text;
- rejection reason;
- candidate resource name;
- matched dialogue offset;
- physical distance to that dialogue record;
- zero-tail length; and
- any stranded Shift-JIS lead byte.

The file is evidence only and is not merged into `translation_inventory.tsv`.

## Validation against the current corpus

A source-guarded pass over the current occurrence inventory and authenticated
Track 2 payload identifies 14 high-confidence shadow artifacts across the game.
This set includes all three Mission 0 fragments that triggered the repair and
the previously suspicious corrupted Mission 0 candidate `T00770`. Legitimate
nearby labels such as `エレベーター`, `ブランデー`, and `モルモット` fail the
zero-tail rule and remain available for translation review.

The filter is intentionally conservative. A candidate that fails any one of
the structural checks remains in `auxiliary.tsv` for human review rather than
being deleted automatically.
