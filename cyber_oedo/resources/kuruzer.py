"""Rebuild the ``KURUZER`` opening-narration resource at its natural size.

``KURUZER`` is one 800-byte named resource (descriptor LBA ``$10F1``).  Its
first dialogue record, at resource offset ``+0x28``, is the opening narration:
``27 28``, Shift-JIS text with nine ``40`` page controls, and a ``00``
terminator ending at ``+0x2E0``.  Everything after the narration (a location
caption and scene commands) is kept byte-for-byte.

Whether any later command addresses bytes after the narration by an
offset relative to the resource start is not yet statically proven.  The
``grow`` relocation test exists to exercise exactly that at runtime.
"""

from __future__ import annotations

import hashlib

from cyber_oedo.text.layout import (
    STOCK_LINE_WIDTH,
    DialoguePage,
    PageBreakPlan,
    PageGeometry,
)
from cyber_oedo.text.stock_english import wrap_stock_lines

KURUZER_NAME = "KURUZER"
KURUZER_LENGTH = 0x320
KURUZER_SHA256 = "ceef76cd70ea8a2d6a4a334863e2b19ffea54b69382a118f081c13babc42f511"
NARRATION_START = 0x28
NARRATION_END = 0x2E0
NARRATION_SHA256 = "93afb245ad8ee5bf0ac1f1e8c712e6c35a4dd3b910725f88df3bb58145dbdc71"
# Heap address observed for KURUZER in the original opening (MesenCE probe).
KURUZER_OBSERVED_LOAD_ADDRESS = 0xC350

DIALOGUE_MARKER = b"\x27\x28"
PAGE_CONTROL = 0x40
TERMINATOR = 0x00
SOURCE_PAGE_BREAKS = 9
# The opening narration window shows three 11-cell rows per page.
NARRATION_GEOMETRY = PageGeometry(width=STOCK_LINE_WIDTH, maximum_lines=3)
class KuruzerError(ValueError):
    """Raised when KURUZER bytes or a replacement record are not acceptable."""


def authenticate_kuruzer(resource: bytes) -> None:
    if len(resource) != KURUZER_LENGTH or hashlib.sha256(resource).hexdigest() != KURUZER_SHA256:
        raise KuruzerError("KURUZER resource differs from the authenticated source")


def original_narration(resource: bytes) -> bytes:
    authenticate_kuruzer(resource)
    return resource[NARRATION_START:NARRATION_END]


def validate_narration_record(record: bytes) -> None:
    """Accept only a well-formed record that ends at its first terminator.

    Low bytes other than the page control would be bytecode with operands, so
    the replacement may contain only two-byte glyphs (lead byte >= ``$80``)
    and ``40`` page controls before the terminator.
    """

    if not record.startswith(DIALOGUE_MARKER) or not record.endswith(bytes((TERMINATOR,))):
        raise KuruzerError("narration record must start with 27 28 and end with 00")
    index = len(DIALOGUE_MARKER)
    end = len(record) - 1
    while index < end:
        value = record[index]
        if value >= 0x80:
            if index + 1 >= end:
                raise KuruzerError("narration record ends inside a two-byte glyph")
            index += 2
        elif value == PAGE_CONTROL:
            index += 1
        else:
            raise KuruzerError(f"unsupported control 0x{value:02X} at record offset {index}")


def rebuild_kuruzer(resource: bytes, narration_record: bytes) -> bytes:
    """Return KURUZER with its narration replaced and all other bytes kept."""

    authenticate_kuruzer(resource)
    validate_narration_record(narration_record)
    return resource[:NARRATION_START] + narration_record + resource[NARRATION_END:]


def doubled_narration_record(resource: bytes) -> bytes:
    """Diagnostic growth record: the original narration twice, page-separated.

    It is renderable by the stock Shift-JIS renderer, so it tests resource
    growth without depending on any English text engine.
    """

    record = original_narration(resource)
    if hashlib.sha256(record).hexdigest() != NARRATION_SHA256:
        raise KuruzerError("KURUZER narration differs from the authenticated source")
    body = record[len(DIALOGUE_MARKER) : -1]
    return DIALOGUE_MARKER + body + bytes((PAGE_CONTROL,)) + body + bytes((TERMINATOR,))


def stock_english_narration_record(resource: bytes, text: str) -> bytes:
    """Compile English narration for the stock fullwidth renderer.

    Pages hold three 11-cell lines.  A ``40`` control waits for the button and
    starts a new row, and the window scrolls rather than clears.  The original
    nine page controls are kept, so the English needs at least ten pages, and
    more controls are added as it needs them.
    """

    lines = wrap_stock_lines(text)
    pages = tuple(
        DialoguePage(lines[index : index + NARRATION_GEOMETRY.maximum_lines])
        for index in range(0, len(lines), NARRATION_GEOMETRY.maximum_lines)
    )
    try:
        plan = PageBreakPlan(
            pages,
            SOURCE_PAGE_BREAKS,
            NARRATION_GEOMETRY,
            allow_added_page_breaks=True,
        )
        record = plan.compile_record(original_narration(resource))
    except ValueError as error:
        raise KuruzerError(str(error)) from error
    validate_narration_record(record)
    return record
