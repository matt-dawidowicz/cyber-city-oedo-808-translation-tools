"""Canonical Shift-JIS byte classification and text helpers.

The toolkit previously carried several subtly different copies of Shift-JIS
lead/trail logic.  This module is the single byte-classification authority for
reconnaissance scanners, structured dialogue parsing, and stock-renderer text
encoding.  Higher-level parsers still decide whether low bytes are text or game
controls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


SHIFT_JIS_TOKEN = (
    rb"(?:"
    rb"[\x20-\x7e]|"
    rb"[\xa1-\xdf]|"
    rb"(?:[\x81-\x9f\xe0-\xef](?:[\x40-\x7e\x80-\xfc]))"
    rb")"
)


def is_shift_jis_lead(value: int) -> bool:
    """Return whether *value* can begin a two-byte Shift-JIS character."""

    return 0x81 <= value <= 0x9F or 0xE0 <= value <= 0xEF


def is_shift_jis_trail(value: int) -> bool:
    """Return whether *value* can trail a two-byte Shift-JIS character."""

    return 0x40 <= value <= 0x7E or 0x80 <= value <= 0xFC


def is_halfwidth_katakana_byte(value: int) -> bool:
    """Return whether *value* is a single-byte halfwidth Katakana token."""

    return 0xA1 <= value <= 0xDF


def token_pattern(minimum_tokens: int) -> re.Pattern[bytes]:
    """Compile the broad Shift-JIS-compatible token-run expression."""

    if minimum_tokens <= 0:
        raise ValueError("minimum_tokens must be positive")
    return re.compile(SHIFT_JIS_TOKEN + rb"{%d,}" % minimum_tokens)


@dataclass(frozen=True, slots=True)
class ScriptMetrics:
    """Unicode shape metrics used by the broad text heuristics."""

    hiragana: int = 0
    katakana: int = 0
    kanji: int = 0
    fullwidth: int = 0
    ascii_printable: int = 0


def script_metrics(text: str) -> ScriptMetrics:
    """Count relevant Unicode classes in one pass over *text*."""

    hiragana = katakana = kanji = fullwidth = ascii_printable = 0
    for character in text:
        value = ord(character)
        if 0x3040 <= value <= 0x309F:
            hiragana += 1
        elif 0x30A0 <= value <= 0x30FF:
            katakana += 1
        if 0x3400 <= value <= 0x9FFF:
            kanji += 1
        if 0xFF01 <= value <= 0xFF60:
            fullwidth += 1
        if 0x20 <= value <= 0x7E:
            ascii_printable += 1
    return ScriptMetrics(
        hiragana=hiragana,
        katakana=katakana,
        kanji=kanji,
        fullwidth=fullwidth,
        ascii_printable=ascii_printable,
    )


def ascii_to_fullwidth(text: str) -> str:
    """Map printable ASCII to strict-Shift-JIS-compatible fullwidth glyphs."""

    converted: list[str] = []
    for character in text:
        codepoint = ord(character)
        if character == " ":
            converted.append("\u3000")
        elif character == "-":
            converted.append("\u2212")
        elif character == "'":
            converted.append("\u2019")
        elif 0x21 <= codepoint <= 0x7E:
            converted.append(chr(codepoint + 0xFEE0))
        else:
            raise ValueError(
                f"unsupported non-printable ASCII character {character!r}"
            )
    return "".join(converted)


def ascii_to_fullwidth_sjis(text: str) -> bytes:
    """Encode printable ASCII through the stock two-byte Shift-JIS path."""

    try:
        return ascii_to_fullwidth(text).encode("shift_jis")
    except UnicodeEncodeError as error:
        raise ValueError("fullwidth text is not strict Shift-JIS") from error
