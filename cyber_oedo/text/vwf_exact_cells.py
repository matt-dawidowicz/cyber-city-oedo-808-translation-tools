"""Seamless whole-line variable-width raster to the stock 16x16 cell token format.

Source art remains the original project-authored font. Layout is measured
before splitting, so letters are never artificially separated at tile edges.
This is a non-release integration mechanism until tested in every game context.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.text.vwf_cells import (
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VWF_TOKEN_CAPACITY,
    VWF_STAGED_CELL_BYTES,
    VWF_CELLS_PER_LINE,
    VwfCellCompileError,
    encode_vwf_token,
)
from cyber_oedo.text.vwf_text import LINE_PIXELS, VwfFont, render_line, wrap_vwf


@dataclass(frozen=True)
class ExactVwfLayout:
    text: str
    stream: bytes
    staged_cells: bytes
    cell_count: int
    unique_cells: int
    line_texts: tuple[str, ...]


def compile_exact_vwf(text: str, font: VwfFont) -> ExactVwfLayout:
    """Split real proportional pixels into VWF tokens for stock redraw/scroll.

    Each token points at a 32-byte 1bpp staged bitmap in Super Card RAM,
    and includes any glyph fragments that cross its 16-pixel boundary.
    The existing VWF loader recognizes each cell by the token itself.
    """
    lines = wrap_vwf(text, font, max_pixels=LINE_PIXELS)
    if len(lines) > 3:
        raise VwfCellCompileError("diagnostic VWF pilot may use up to three lines")
    entries: list[bytes] = []
    by_cell: dict[bytes, int] = {}
    stream = bytearray()
    total_cells = 0
    for line_index, value in enumerate(lines):
        rendered = render_line(value, font)
        needed = (rendered.pixel_width + 15) // 16
        if not 1 <= needed <= VWF_CELLS_PER_LINE:
            raise VwfCellCompileError("exact VWF line exceeds 11 stock cells")
        stream.extend(VWF_MODE_SIGNATURE)
        for cell_index in range(needed):
            shift = LINE_PIXELS - 16 * (cell_index + 1)
            rows = [((row >> shift) & 0xFFFF) for row in rendered.bitmap_rows]
            payload = b"".join(row.to_bytes(2, "big") for row in rows)
            if len(payload) != VWF_STAGED_CELL_BYTES:
                raise AssertionError("VWF staging-cell size must remain 32 bytes")
            index = by_cell.get(payload)
            if index is None:
                index = len(entries)
                if index >= VWF_TOKEN_CAPACITY:
                    raise VwfCellCompileError("exact VWF dictionary exceeds Card RAM")
                by_cell[payload] = index
                entries.append(payload)
            stream.extend(encode_vwf_token(index))
        stream.extend(VWF_SEGMENT_END_TOKEN.to_bytes(2, "big"))
        total_cells += needed
        if line_index < len(lines) - 1:
            stream.append(0x40)  # preserve stock line advance
    stream.append(0)
    return ExactVwfLayout(
        text=text,
        stream=bytes(stream),
        staged_cells=b"".join(entries),
        cell_count=total_cells,
        unique_cells=len(entries),
        line_texts=lines,
    )
