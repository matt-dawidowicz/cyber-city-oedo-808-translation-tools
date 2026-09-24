"""Decode the row-addressed information/OEDONET presentation stream.

The stream is a sequence of NUL-delimited records.  Most visible records begin
with an X/column byte and a row byte followed by Shift-JIS.  A small, finite
set of binary formatting records surrounds those text records.  This module
keeps their byte identities explicit instead of misclassifying them as text
opcodes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PresentationRecord:
    offset: int
    raw: bytes
    kind: str
    x: int | None = None
    row: int | None = None
    text: str | None = None
    formatting_role: str | None = None


# These records are stable across the observed information/OEDONET pages.
# The names describe their structural placement.  They intentionally do not
# invent lower-level VDC semantics that still require a live trace.
KNOWN_FORMATTING_RECORDS: dict[bytes, str] = {
    bytes.fromhex("02 01 05 01 06"): "screen_preamble",
    bytes.fromhex("50"): "screen_preamble_tail",
    bytes.fromhex("08 01 20"): "heading_layout",
    bytes.fromhex("01 70 08"): "body_layout",
    bytes.fromhex("08 07"): "sidebar_layout_a",
    bytes.fromhex("14 08 0B 09"): "sidebar_layout_b",
    bytes.fromhex("08"): "sidebar_or_footer_boundary",
    bytes.fromhex("08 09 03"): "stream_end",
    bytes.fromhex("08 09 0A"): "next_information_page",
    bytes.fromhex("08 03 0A"): "next_media_mix_page",
}


def _decode_printable_shift_jis(raw: bytes) -> str | None:
    if not raw:
        return None
    try:
        text = raw.decode("shift_jis")
    except UnicodeDecodeError:
        return None
    if not all(ord(character) >= 0x20 and character != "\x7f" for character in text):
        return None
    return text


def decode_presentation_stream(data: bytes) -> tuple[PresentationRecord, ...]:
    """Decode every non-empty NUL-delimited presentation record."""

    rows: list[PresentationRecord] = []
    cursor = 0
    while cursor < len(data):
        end = data.find(b"\x00", cursor)
        if end < 0:
            raw = data[cursor:]
            next_cursor = len(data)
        else:
            raw = data[cursor:end]
            next_cursor = end + 1

        if not raw:
            cursor = next_cursor
            continue

        role = KNOWN_FORMATTING_RECORDS.get(raw)
        if role is not None:
            rows.append(
                PresentationRecord(
                    offset=cursor,
                    raw=raw,
                    kind="formatting",
                    formatting_role=role,
                )
            )
            cursor = next_cursor
            continue

        if len(raw) >= 3:
            text = _decode_printable_shift_jis(raw[2:])
            if text is not None:
                rows.append(
                    PresentationRecord(
                        offset=cursor,
                        raw=raw,
                        kind="text",
                        x=raw[0],
                        row=raw[1],
                        text=text,
                    )
                )
                cursor = next_cursor
                continue

        rows.append(
            PresentationRecord(
                offset=cursor,
                raw=raw,
                kind="unknown_binary",
            )
        )
        cursor = next_cursor

    return tuple(rows)


def unknown_binary_records(
    records: tuple[PresentationRecord, ...],
) -> tuple[PresentationRecord, ...]:
    return tuple(record for record in records if record.kind == "unknown_binary")
