"""Parse the game's ``27 28`` dialogue bytecode with operand awareness."""

from __future__ import annotations

from cyber_oedo.text.sjis import (
    is_halfwidth_katakana_byte,
    is_shift_jis_lead,
    is_shift_jis_trail,
)

from .ast import (
    ControlCommand,
    DialogueBody,
    DialogueNode,
    DialogueRecord,
    TextRun,
)
from .opcodes import (
    DEFAULT_PARSE_LIMIT,
    DIALOGUE_MARKER,
    DIALOGUE_TERMINATOR,
    opcode_spec,
)


def _decode_one_glyph(
    data: object,
    position: int,
) -> tuple[bytes, str] | None:
    """Decode one valid source glyph beginning at *position*."""

    size = len(data)  # type: ignore[arg-type]
    value = data[position]  # type: ignore[index]
    if (
        is_shift_jis_lead(value)
        and position + 1 < size
        and is_shift_jis_trail(
            data[position + 1]  # type: ignore[index]
        )
    ):
        raw = bytes(
            data[position : position + 2]  # type: ignore[index]
        )
    elif is_halfwidth_katakana_byte(value):
        raw = bytes((value,))
    else:
        return None
    try:
        return raw, raw.decode("shift_jis")
    except UnicodeDecodeError:
        return None


def parse_dialogue_body(
    data: object,
    start: int,
    limit: int = DEFAULT_PARSE_LIMIT,
    *,
    allow_unknown_controls: bool = False,
) -> DialogueBody | None:
    """Parse a dialogue body while respecting command operand widths.

    ``start`` points to the first byte after ``27 28``. A zero byte ends the
    record only at command/text dispatch level. Zeros consumed as command
    operands therefore cannot truncate a record.
    """

    if start < 0:
        raise ValueError("start must be non-negative")
    if limit <= 0:
        raise ValueError("limit must be positive")

    position = start
    size = len(data)  # type: ignore[arg-type]
    nodes: list[DialogueNode] = []
    text_offset: int | None = None
    text_raw = bytearray()
    text_parts: list[str] = []
    text_characters = 0

    def flush_text() -> None:
        """Append the pending contiguous text run, if one exists."""

        nonlocal text_offset, text_characters
        if text_offset is None:
            return
        nodes.append(
            TextRun(
                offset=text_offset,
                raw=bytes(text_raw),
                text="".join(text_parts),
                character_count=text_characters,
            )
        )
        text_offset = None
        text_raw.clear()
        text_parts.clear()
        text_characters = 0

    while position < size and position - start < limit:
        value = data[position]  # type: ignore[index]
        if value == DIALOGUE_TERMINATOR:
            flush_text()
            return DialogueBody(start, position, tuple(nodes))

        glyph = _decode_one_glyph(data, position)
        if glyph is not None:
            raw, character = glyph
            if text_offset is None:
                text_offset = position
            text_raw.extend(raw)
            text_parts.append(character)
            text_characters += 1
            position += len(raw)
            continue

        if 0 < value < 0x80:
            flush_text()
            spec = opcode_spec(value)
            if spec is None:
                if not allow_unknown_controls:
                    return None
                operand_count = 0
                name = None
            else:
                operand_count = spec.operand_bytes
                name = spec.name
            command_end = position + 1 + operand_count
            if command_end > size or command_end - start > limit:
                return None
            operands = bytes(
                data[position + 1 : command_end]  # type: ignore[index]
            )
            nodes.append(
                ControlCommand(
                    offset=position,
                    opcode=value,
                    operands=operands,
                    name=name,
                )
            )
            position = command_end
            continue

        return None

    return None


def parse_dialogue_record(
    data: object,
    marker_offset: int,
    limit: int = DEFAULT_PARSE_LIMIT,
    *,
    allow_unknown_controls: bool = False,
) -> DialogueRecord | None:
    """Parse one complete record beginning at its ``27 28`` marker."""

    if marker_offset < 0:
        raise ValueError("marker_offset must be non-negative")
    size = len(data)  # type: ignore[arg-type]
    marker_end = marker_offset + len(DIALOGUE_MARKER)
    if marker_end > size:
        return None
    marker = bytes(
        data[marker_offset:marker_end]  # type: ignore[index]
    )
    if marker != DIALOGUE_MARKER:
        return None
    body = parse_dialogue_body(
        data,
        marker_end,
        limit,
        allow_unknown_controls=allow_unknown_controls,
    )
    if body is None:
        return None
    return DialogueRecord(
        marker_offset=marker_offset,
        body=body,
    )


__all__ = ["parse_dialogue_body", "parse_dialogue_record"]
