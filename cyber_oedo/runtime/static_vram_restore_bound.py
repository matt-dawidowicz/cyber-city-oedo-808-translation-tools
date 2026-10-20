"""Derive static upper bounds for dialogue-owned exploration VRAM damage.

The live dirty-range profiler remains authoritative for promotion.  This module
uses already source-guarded renderer geometry to quantify address families that
can be bounded without a new emulator capture.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from cyber_oedo.runtime.dialogue_residency import (
    PORTRAIT_VRAM_BYTES,
    PORTRAIT_VRAM_END_WORD_EXCLUSIVE,
    PORTRAIT_VRAM_START_WORD,
    SCENE_VRAM_BYTES,
)

TEXT_ROWS = 3
TEXT_COLUMNS = 12
TEXT_CELLS = TEXT_ROWS * TEXT_COLUMNS
GLYPH_BASE_WORD = 0x6D00
GLYPH_SLOT_STRIDE_WORDS = 0x40
GLYPH_STREAM_CALLS = 2
GLYPH_WORDS_PER_STREAM_CALL = 16
GLYPH_WORDS_WRITTEN_PER_CELL = GLYPH_STREAM_CALLS * GLYPH_WORDS_PER_STREAM_CALL
WORD_BYTES = 2
BAT_BASE_WORD = 0x7900

LIVE_BAR_TOTAL_DIRTY_BYTES = 33163
LIVE_BAR_LOW_VRAM_DIRTY_BYTES = 938
LIVE_BAR_STOCK_REGION_DIRTY_BYTES = 32225
LIVE_BAR_STOCK_RESTORE_START_BYTE = 0x1200
LIVE_BAR_STOCK_RESTORE_BYTES = 0xEE00
LIVE_BAR_STOCK_RESTORE_FRAMES = 551
LIVE_BAR_SELECTIVE_RESTORE_FRAMES = 412
LIVE_BAR_SELECTIVE_SPANS = (
    {
        "source_lba": 0x22E8,
        "destination_word": 0x0900,
        "start_byte": 0x1200,
        "end_byte_inclusive": 0xA01F,
        "length_bytes": 0x8E20,
        "measured_frames": 333,
    },
    {
        "source_lba": 0x2301,
        "destination_word": 0x6D00,
        "start_byte": 0xDA00,
        "end_byte_inclusive": 0xF3FF,
        "length_bytes": 0x1A00,
        "measured_frames": 79,
    },
)


def glyph_dirty_ranges() -> tuple[tuple[int, int], ...]:
    """Return exact sparse glyph-pattern word ranges for all 36 grid slots."""

    return tuple(
        (
            GLYPH_BASE_WORD + index * GLYPH_SLOT_STRIDE_WORDS,
            GLYPH_BASE_WORD
            + index * GLYPH_SLOT_STRIDE_WORDS
            + GLYPH_WORDS_WRITTEN_PER_CELL,
        )
        for index in range(TEXT_CELLS)
    )


def build_static_vram_restore_bound() -> dict[str, object]:
    glyphs = glyph_dirty_ranges()
    glyph_dirty_words = sum(end - start for start, end in glyphs)
    glyph_envelope_start = glyphs[0][0]
    glyph_envelope_end = glyphs[-1][1]
    portrait_words = PORTRAIT_VRAM_BYTES // WORD_BYTES
    known_sparse_bytes = PORTRAIT_VRAM_BYTES + glyph_dirty_words * WORD_BYTES
    known_envelope_bytes = (
        PORTRAIT_VRAM_BYTES
        + (glyph_envelope_end - glyph_envelope_start) * WORD_BYTES
    )

    return {
        "full_scene_restore_bytes": SCENE_VRAM_BYTES,
        "portrait": {
            "start_word": f"$%04X" % PORTRAIT_VRAM_START_WORD,
            "end_word_inclusive": f"$%04X" % (PORTRAIT_VRAM_END_WORD_EXCLUSIVE - 1),
            "words": portrait_words,
            "bytes": PORTRAIT_VRAM_BYTES,
            "address_range_reused_by_multiple_portraits": True,
        },
        "glyph_patterns": {
            "grid_cells": TEXT_CELLS,
            "base_word": f"$%04X" % GLYPH_BASE_WORD,
            "slot_stride_words": GLYPH_SLOT_STRIDE_WORDS,
            "stream_calls_per_render": GLYPH_STREAM_CALLS,
            "words_per_stream_call": GLYPH_WORDS_PER_STREAM_CALL,
            "words_written_per_cell": GLYPH_WORDS_WRITTEN_PER_CELL,
            "bytes_written_per_cell": GLYPH_WORDS_WRITTEN_PER_CELL * WORD_BYTES,
            "sparse_dirty_words_all_slots": glyph_dirty_words,
            "sparse_dirty_bytes_all_slots": glyph_dirty_words * WORD_BYTES,
            "envelope_start_word": f"$%04X" % glyph_envelope_start,
            "envelope_end_word_inclusive": f"$%04X" % (glyph_envelope_end - 1),
            "envelope_bytes": (glyph_envelope_end - glyph_envelope_start) * WORD_BYTES,
            "ranges": [
                {
                    "cell": index,
                    "start_word": f"$%04X" % start,
                    "end_word_inclusive": f"$%04X" % (end - 1),
                }
                for index, (start, end) in enumerate(glyphs)
            ],
        },
        "bat": {
            "base_word": f"$%04X" % BAT_BASE_WORD,
            "exact_union_static_bound": None,
            "reason": (
                "The one-word BAT writer and base are source-guarded, but the "
                "complete positioned/redraw caller geometry is not represented "
                "as exact per-cell destination ranges in the maintained static "
                "model. Keep BAT restoration live-profile-driven rather than "
                "inventing a contiguous bound."
            ),
        },
        "known_without_bat": {
            "sparse_bytes": known_sparse_bytes,
            "sparse_percent_of_full_scene": known_sparse_bytes / SCENE_VRAM_BYTES * 100.0,
            "portrait_plus_one_glyph_envelope_bytes": known_envelope_bytes,
            "envelope_percent_of_full_scene": known_envelope_bytes / SCENE_VRAM_BYTES * 100.0,
            "interpretation": (
                "Even restoring the entire glyph address envelope instead of its "
                "sparse writes leaves portrait+glyph restoration far below the "
                "60,928-byte stock scene transfer. BAT damage must be added from "
                "live or deeper caller proof before this becomes a patch plan."
            ),
        },
        "live_bar_capture": {
            "method": (
                "MesenCE 2.2.1 deterministic bartender replay from the retained "
                "bartender probe state; 64 KiB VRAM snapshots were taken before "
                "Button I and immediately before the stock $22E8 restore. A "
                "same-duration no-dialogue control changed zero VRAM bytes."
            ),
            "total_dirty_bytes": LIVE_BAR_TOTAL_DIRTY_BYTES,
            "dirty_below_stock_restore_start_bytes": LIVE_BAR_LOW_VRAM_DIRTY_BYTES,
            "dirty_inside_stock_restore_region_bytes": LIVE_BAR_STOCK_REGION_DIRTY_BYTES,
            "stock_restore": {
                "source_lba": "$22E8",
                "destination_word": "$0900",
                "destination_byte": "$1200",
                "bytes": LIVE_BAR_STOCK_RESTORE_BYTES,
                "frames": LIVE_BAR_STOCK_RESTORE_FRAMES,
                "seconds": LIVE_BAR_STOCK_RESTORE_FRAMES / 60.0,
            },
            "selective_two_span_candidate": {
                "spans": [
                    {
                        **span,
                        "source_lba": f"$%04X" % span["source_lba"],
                        "destination_word": f"$%04X" % span["destination_word"],
                        "start_byte": f"$%04X" % span["start_byte"],
                        "end_byte_inclusive": f"$%04X" % span["end_byte_inclusive"],
                    }
                    for span in LIVE_BAR_SELECTIVE_SPANS
                ],
                "transfer_bytes": sum(
                    span["length_bytes"] for span in LIVE_BAR_SELECTIVE_SPANS
                ),
                "bytes_skipped_vs_stock": (
                    LIVE_BAR_STOCK_RESTORE_BYTES
                    - sum(span["length_bytes"] for span in LIVE_BAR_SELECTIVE_SPANS)
                ),
                "frames": LIVE_BAR_SELECTIVE_RESTORE_FRAMES,
                "seconds": LIVE_BAR_SELECTIVE_RESTORE_FRAMES / 60.0,
                "frames_saved": (
                    LIVE_BAR_STOCK_RESTORE_FRAMES - LIVE_BAR_SELECTIVE_RESTORE_FRAMES
                ),
                "seconds_saved": (
                    LIVE_BAR_STOCK_RESTORE_FRAMES - LIVE_BAR_SELECTIVE_RESTORE_FRAMES
                )
                / 60.0,
                "post_restore_vram_matches_stock": True,
                "visual_bar_return_verified": True,
                "release_safe": False,
                "interpretation": (
                    "The live capture invalidates the earlier assumption that "
                    "portrait+glyph geometry approximates total transition damage: "
                    "dialogue/transition code dirties much broader VRAM. Even so, "
                    "eight of the stock 30 source sectors are completely untouched. "
                    "Two legitimate BIOS CD-to-VRAM transfers reproduced the stock "
                    "post-restore 64 KiB VRAM image byte-for-byte while saving "
                    "139 frames / 2.317 seconds."
                ),
            },
        },
        "source_note": (
            "The renderer's guarded $5772 loop writes sixteen VDC words per call "
            "and $570C invokes it twice, so each rendered grid slot writes 32 "
            "words / 64 bytes despite a $40-word allocation stride. Live capture "
            "shows these statically bounded renderer writes are only a subset of "
            "the complete transition-time VRAM damage."
        ),
        "release_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Quantify static dialogue VRAM dirty-range upper bounds."
    )
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = build_static_vram_restore_bound()
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
