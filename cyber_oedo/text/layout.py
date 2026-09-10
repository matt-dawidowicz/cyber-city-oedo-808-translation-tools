"""Stock-renderer English encoding, wrapping, and page compilation."""

from __future__ import annotations

from dataclasses import dataclass
from cyber_oedo.text.extract_dialogue import parse_record


DIALOGUE_MARKER = bytes.fromhex('27 28')


DIALOGUE_TERMINATOR = 0


PAGE_CONTROL = 64


STOCK_LINE_WIDTH = 11


def ascii_to_fullwidth_sjis(text: str) -> bytes:
    """Encode printable ASCII through the stock two-byte glyph path.

    Args:
        text: Printable ASCII text. Spaces become ideographic spaces.

    Returns:
        Strict Shift-JIS bytes containing no single-byte ASCII glyphs.

    Raises:
        ValueError: If a character is not printable ASCII or the mapped
            fullwidth glyph is unavailable in strict Shift-JIS.

    Design Decisions:
        Hyphen and apostrophe use the same encodable alternatives as the
        stable human-test builder. Python's strict codec lacks fullwidth
        hyphen-minus and apostrophe.
    """
    converted: list[str] = []
    for character in text:
        codepoint = ord(character)
        if character == ' ':
            converted.append('\u3000')
        elif character == '-':
            converted.append('−')
        elif character == "'":
            converted.append('’')
        elif 33 <= codepoint <= 126:
            converted.append(chr(codepoint + 65248))
        else:
            raise ValueError(f'unsupported ASCII character {character!r}')
    try:
        return ''.join(converted).encode('shift_jis')
    except UnicodeEncodeError as error:
        raise ValueError('fullwidth text is not strict Shift-JIS') from error


def wrap_english_lines(text: str, width: int) -> tuple[str, ...]:
    """Wrap single-spaced English without splitting a word.

    Args:
        text: Printable, single-spaced English without outer whitespace.
        width: Positive stock-renderer cell width.

    Returns:
        Unpadded visual lines in source order.

    Raises:
        ValueError: If the text is empty, spacing is ambiguous, a character is
            unsupported, or a word exceeds the selected width.
    """
    if width <= 0:
        raise ValueError('line width must be positive')
    words = text.split(' ')
    if not text or text.strip() != text or any((not word for word in words)):
        raise ValueError('English must use single spaces without outer space')
    ascii_to_fullwidth_sjis(text)
    too_wide = [word for word in words if len(word) > width]
    if too_wide:
        raise ValueError(f'word exceeds {width}-cell line: {too_wide[0]!r}')
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class PageGeometry:
    """Describe one confirmed stock-renderer dialogue window.

    Attributes:
        width: Visible fullwidth cells per line.
        maximum_lines: Maximum lines allowed before a page control.
        page_control: Existing interpreter command used between pages.
    """
    width: int
    maximum_lines: int
    page_control: int = PAGE_CONTROL

    def __post_init__(self) -> None:
        """Validate display bounds and the low-byte page command."""
        if self.width <= 0:
            raise ValueError('page width must be positive')
        if self.maximum_lines <= 0:
            raise ValueError('maximum page lines must be positive')
        if not 0 < self.page_control < 128:
            raise ValueError('page control must be a nonzero low byte')


@dataclass(frozen=True, slots=True)
class DialoguePage:
    """Store translator-approved visual lines for one dialogue page.

    Attributes:
        lines: Explicit English lines in display order.
    """
    lines: tuple[str, ...]

    def compile(self, geometry: PageGeometry) -> bytes:
        """Encode lines with stock automatic-wrap padding.

        Args:
            geometry: Confirmed cell width and maximum visible line count.

        Returns:
            Fullwidth Shift-JIS bytes. Every non-final line is padded to the
            exact cell width so the stock cursor advances at a word boundary.

        Raises:
            ValueError: If the page is empty, too tall, or contains an invalid
                or over-width line.
        """
        if not self.lines:
            raise ValueError('dialogue page must contain at least one line')
        if len(self.lines) > geometry.maximum_lines:
            raise ValueError('dialogue page exceeds its visible line count')
        compiled = bytearray()
        for index, line in enumerate(self.lines):
            if not line or line.strip() != line:
                raise ValueError('page lines must not be empty or padded')
            if '  ' in line:
                raise ValueError('page lines must use single spaces')
            if len(line) > geometry.width:
                raise ValueError('page line exceeds the stock cell width')
            displayed = line.ljust(geometry.width) if index < len(self.lines) - 1 else line
            compiled.extend(ascii_to_fullwidth_sjis(displayed))
        return bytes(compiled)


def wrap_dialogue_page(text: str, geometry: PageGeometry) -> DialoguePage:
    """Wrap one natural-English page under confirmed geometry.

    Args:
        text: Natural English intended to remain on one page.
        geometry: Confirmed cell width and visible line count.

    Returns:
        A page with explicit unpadded visual lines.

    Raises:
        ValueError: If wrapping exceeds the page height or text is invalid.
    """
    lines = wrap_english_lines(text, geometry.width)
    if len(lines) > geometry.maximum_lines:
        raise ValueError('wrapped English exceeds one dialogue page')
    return DialoguePage(lines)


@dataclass(frozen=True, slots=True)
class PageBreakPlan:
    """Compile a page-only record without changing the renderer.

    Attributes:
        pages: Translator-approved pages in playback order.
        source_page_breaks: Number of page controls in the guarded source.
        geometry: Confirmed renderer geometry and page-control byte.
        allow_added_page_breaks: Whether expansion may add page controls.

    Notes:
        This model intentionally accepts only records whose existing controls
        are all the selected page command. Mixed pause, input, or audio
        controls require a record-specific control template instead.
    """
    pages: tuple[DialoguePage, ...]
    source_page_breaks: int
    geometry: PageGeometry
    allow_added_page_breaks: bool = False

    def __post_init__(self) -> None:
        """Validate page counts before source bytes are inspected."""
        if not self.pages:
            raise ValueError('page-break plan must contain at least one page')
        if self.source_page_breaks < 0:
            raise ValueError('source page-break count must not be negative')
        replacement_breaks = len(self.pages) - 1
        if replacement_breaks < self.source_page_breaks:
            raise ValueError('page-break plan must not remove source pages')
        if replacement_breaks > self.source_page_breaks and (not self.allow_added_page_breaks):
            raise ValueError('additional page breaks require explicit opt-in')

    def compile_record(self, source_record: bytes) -> bytes:
        """Compile fullwidth English after validating source controls.

        Args:
            source_record: Exact marker-through-terminator source bytes.

        Returns:
            A relocated record using the original marker, stock Shift-JIS
            glyphs, and the confirmed page command between pages.

        Raises:
            ValueError: If the source is malformed, has mixed controls, has a
                different page count, or a page fails geometry validation.
        """
        parsed = parse_record(source_record, len(DIALOGUE_MARKER), limit=max(1, len(source_record)))
        if not source_record.startswith(DIALOGUE_MARKER):
            raise ValueError('source record is missing its dialogue marker')
        if parsed is None or parsed.end_offset != len(source_record) - 1:
            raise ValueError('source record is malformed or has trailing data')
        expected_controls = (self.geometry.page_control,) * self.source_page_breaks
        if parsed.controls != expected_controls:
            raise ValueError('source record is not a page-only control stream')
        body = bytearray()
        for index, page in enumerate(self.pages):
            body.extend(page.compile(self.geometry))
            if index < len(self.pages) - 1:
                body.append(self.geometry.page_control)
        return DIALOGUE_MARKER + bytes(body) + bytes((DIALOGUE_TERMINATOR,))
