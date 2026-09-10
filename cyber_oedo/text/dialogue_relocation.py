"""Compatibility facade for split stock-layout and relocation APIs."""

from cyber_oedo.text.layout import (
    DIALOGUE_MARKER,
    DIALOGUE_TERMINATOR,
    PAGE_CONTROL,
    STOCK_LINE_WIDTH,
    DialoguePage,
    PageBreakPlan,
    PageGeometry,
    ascii_to_fullwidth_sjis,
    wrap_dialogue_page,
    wrap_english_lines,
)
from cyber_oedo.text.relocation import (
    DialogueRelocationPlan,
    PointerSite,
    RelocationArea,
    find_u16_pointer_candidates,
)

__all__ = [
    "DIALOGUE_MARKER",
    "DIALOGUE_TERMINATOR",
    "PAGE_CONTROL",
    "STOCK_LINE_WIDTH",
    "DialoguePage",
    "PageBreakPlan",
    "PageGeometry",
    "ascii_to_fullwidth_sjis",
    "wrap_dialogue_page",
    "wrap_english_lines",
    "DialogueRelocationPlan",
    "PointerSite",
    "RelocationArea",
    "find_u16_pointer_candidates",
]
