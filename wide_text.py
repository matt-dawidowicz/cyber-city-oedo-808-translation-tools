"""Compile proposed 22-column English escape streams for the engine lab.

This is a host-side format prototype only.  It deliberately does not create
payload patches or modify CloneCD images.  A runtime-proven HuC6280 renderer
must be able to consume the format before any encoded output may enter a game
build.
"""

from __future__ import annotations

from dataclasses import dataclass

WIDE_START = 0xFF
WIDE_END = 0xFE
WIDE_NEWLINE = 0x0A
WIDE_LINE_WIDTH = 22
_PRINTABLE_ASCII = frozenset(range(0x20, 0x7F))


class WideTextError(ValueError):
    """Report wording that cannot be represented by the proposed format."""


def wrap_wide_english(
    text: str,
    width: int = WIDE_LINE_WIDTH,
) -> tuple[str, ...]:
    """Wrap normalized ASCII English into fixed-width 8x16 display lines.

    The runtime implementation is expected to advance eight pixels per
    printable byte while in escape mode.  The function performs no byte-size
    fitting because the full translation corpus is intentionally independent
    of current source-record capacity.
    """

    if not isinstance(text, str) or not text:
        raise WideTextError("text must be a non-empty string")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise WideTextError("width must be a positive integer")
    if text != text.strip() or "  " in text:
        raise WideTextError("text must use single interior spaces")
    if any(ord(character) not in _PRINTABLE_ASCII for character in text):
        raise WideTextError("text must use printable ASCII only")

    lines: list[str] = []
    line = ""
    for word in text.split(" "):
        if len(word) > width:
            raise WideTextError(
                f"word {word!r} exceeds {width}-column wide-text line"
            )
        candidate = word if not line else f"{line} {word}"
        if len(candidate) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class WideTextPrototype:
    """Represent one proposed renderer-escape stream without game insertion.

    ``WIDE_START`` and ``WIDE_END`` are provisional values.  They are absent
    from the 3,799 structured dialogue records in the generated corpus, but
    runtime control tracing must still prove that they are safe escape values.
    """

    english: str
    width: int = WIDE_LINE_WIDTH

    @property
    def lines(self) -> tuple[str, ...]:
        """Return the proposed 22-column word wrapping."""

        return wrap_wide_english(self.english, self.width)

    @property
    def encoded(self) -> bytes:
        """Return a provisional one-byte ASCII escape stream."""

        body = bytes((WIDE_NEWLINE,)).join(
            line.encode("ascii") for line in self.lines
        )
        return bytes((WIDE_START,)) + body + bytes((WIDE_END,))
