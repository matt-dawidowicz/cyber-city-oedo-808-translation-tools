"""Compile English for the stock fullwidth Shift-JIS dialogue renderer.

The stock renderer draws 11 fullwidth cells per row.  A ``40`` control waits
for the button and starts a new row, and the three-row window scrolls rather
than clears (observed live in the opening narration).  This module wraps
English to that grid and recompiles page-only dialogue records, keeping every
source page control and adding more where the English needs them.
"""

from __future__ import annotations

import re

from cyber_oedo.text.extract_dialogue import parse_record
from cyber_oedo.text.layout import (
    PAGE_CONTROL,
    STOCK_LINE_WIDTH,
    DialoguePage,
    PageBreakPlan,
    PageGeometry,
)

# Three 11-cell rows per page, as in the opening narration window.
STOCK_PAGE_GEOMETRY = PageGeometry(width=STOCK_LINE_WIDTH, maximum_lines=3)
SOFT_HYPHEN = "­"
# Break opportunities: after a hyphen, an em dash, or a translator's soft
# hyphen (U+00AD), which shows as "-" only when the line breaks there.
_BREAK_AFTER = re.compile("[^—­-]*[—­-]|[^—­-]+")
# A forced break inside an unmarked long word leaves at least this many letters.
_MIN_FRAGMENT = 5


class StockEnglishError(ValueError):
    """Raised when English cannot be compiled for a source record."""


def wrap_stock_lines(text: str, width: int = STOCK_LINE_WIDTH) -> tuple[str, ...]:
    """Wrap English for the fixed-cell stock renderer.

    Lines break at spaces, after a hyphen or em dash, or at a soft hyphen.
    A word longer than a whole line with no marked break is hyphenated as a
    last resort, filling the current line without leaving a tiny fragment.
    """

    if not text or text.strip() != text or "  " in text:
        raise StockEnglishError("English must be single-spaced without outer space")
    lines: list[str] = []
    current = ""
    soft_pending = False
    for word in text.split(" "):
        for index, raw_piece in enumerate(_BREAK_AFTER.findall(word)):
            soft = raw_piece.endswith(SOFT_HYPHEN)
            piece = raw_piece.rstrip(SOFT_HYPHEN)
            separator = " " if index == 0 and current else ""
            needed = len(piece) + (1 if soft else 0)
            if len(current) + len(separator) + needed <= width:
                current += separator + piece
                soft_pending = soft
                continue
            if current:
                lines.append(current + ("-" if soft_pending and not separator else ""))
            current = ""
            while len(piece) > width:
                cut = width - 1
                if len(piece) - cut < _MIN_FRAGMENT:
                    cut = max(_MIN_FRAGMENT, len(piece) - _MIN_FRAGMENT)
                lines.append(piece[:cut] + "-")
                piece = piece[cut:]
            current = piece
            soft_pending = soft
    lines.append(current)
    return tuple(line for line in lines if line)


def page_controls(source_record: bytes) -> int:
    """Return how many ``40`` controls a page-only source record has.

    Raises when the record has any other control, because waits, voice cues
    and inserted names need a record-specific control template.
    """

    parsed = parse_record(source_record, 2, limit=len(source_record) - 2, allow_unknown_controls=False)
    if parsed is None or parsed.end_offset != len(source_record) - 1:
        raise StockEnglishError("source record is malformed or has trailing data")
    if any(control != PAGE_CONTROL for control in parsed.controls):
        raise StockEnglishError("source record has controls other than page breaks")
    return len(parsed.controls)


def compile_stock_record(
    source_record: bytes,
    text: str,
    geometry: PageGeometry = STOCK_PAGE_GEOMETRY,
) -> bytes:
    """Compile English into a new ``27 28 ... 00`` record for *source_record*."""

    breaks = page_controls(source_record)
    lines = wrap_stock_lines(" ".join(text.split()), geometry.width)
    pages = tuple(
        DialoguePage(lines[index : index + geometry.maximum_lines])
        for index in range(0, len(lines), geometry.maximum_lines)
    )
    try:
        plan = PageBreakPlan(pages, breaks, geometry, allow_added_page_breaks=True)
        return plan.compile_record(source_record)
    except ValueError as error:
        raise StockEnglishError(str(error)) from error
