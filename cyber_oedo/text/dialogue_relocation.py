"""Plan stock-renderer dialogue pages and guarded pointer relocations.

The dialogue interpreter treats low bytes as commands, so English must remain
two-byte Shift-JIS when the original renderer is used. This module compiles
translator-chosen 11-cell lines, inserts only the already observed page
control, and models relocation as an explicit set of pointer updates plus an
exact destination guard.

Nothing in this module discovers ownership automatically. Pointer candidates,
constant-fill tails, and named-resource boundaries remain evidence for review.
An active plan requires every pointer site and every destination byte to be
supplied explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass

from cdrom_mode1 import PayloadPatch
from extract_dialogue import parse_record


DIALOGUE_MARKER = bytes.fromhex("27 28")
DIALOGUE_TERMINATOR = 0x00
PAGE_CONTROL = 0x40
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
                f"unsupported ASCII character {character!r}"
            )
    try:
        return "".join(converted).encode("shift_jis")
    except UnicodeEncodeError as error:
        raise ValueError("fullwidth text is not strict Shift-JIS") from error


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
        raise ValueError("line width must be positive")
    words = text.split(" ")
    if not text or text.strip() != text or any(not word for word in words):
        raise ValueError("English must use single spaces without outer space")
    ascii_to_fullwidth_sjis(text)
    too_wide = [word for word in words if len(word) > width]
    if too_wide:
        raise ValueError(
            f"word exceeds {width}-cell line: {too_wide[0]!r}"
        )

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
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
            raise ValueError("page width must be positive")
        if self.maximum_lines <= 0:
            raise ValueError("maximum page lines must be positive")
        if not 0 < self.page_control < 0x80:
            raise ValueError("page control must be a nonzero low byte")


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
            raise ValueError("dialogue page must contain at least one line")
        if len(self.lines) > geometry.maximum_lines:
            raise ValueError("dialogue page exceeds its visible line count")

        compiled = bytearray()
        for index, line in enumerate(self.lines):
            if not line or line.strip() != line:
                raise ValueError("page lines must not be empty or padded")
            if "  " in line:
                raise ValueError("page lines must use single spaces")
            if len(line) > geometry.width:
                raise ValueError("page line exceeds the stock cell width")
            displayed = (
                line.ljust(geometry.width)
                if index < len(self.lines) - 1
                else line
            )
            compiled.extend(ascii_to_fullwidth_sjis(displayed))
        return bytes(compiled)


def wrap_dialogue_page(
    text: str,
    geometry: PageGeometry,
) -> DialoguePage:
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
        raise ValueError("wrapped English exceeds one dialogue page")
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
            raise ValueError("page-break plan must contain at least one page")
        if self.source_page_breaks < 0:
            raise ValueError("source page-break count must not be negative")
        replacement_breaks = len(self.pages) - 1
        if replacement_breaks < self.source_page_breaks:
            raise ValueError("page-break plan must not remove source pages")
        if (
            replacement_breaks > self.source_page_breaks
            and not self.allow_added_page_breaks
        ):
            raise ValueError("additional page breaks require explicit opt-in")

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

        parsed = parse_record(
            source_record,
            len(DIALOGUE_MARKER),
            limit=max(1, len(source_record)),
        )
        if not source_record.startswith(DIALOGUE_MARKER):
            raise ValueError("source record is missing its dialogue marker")
        if parsed is None or parsed.end_offset != len(source_record) - 1:
            raise ValueError("source record is malformed or has trailing data")
        expected_controls = (
            self.geometry.page_control,
        ) * self.source_page_breaks
        if parsed.controls != expected_controls:
            raise ValueError("source record is not a page-only control stream")

        body = bytearray()
        for index, page in enumerate(self.pages):
            body.extend(page.compile(self.geometry))
            if index < len(self.pages) - 1:
                body.append(self.geometry.page_control)
        return (
            DIALOGUE_MARKER
            + bytes(body)
            + bytes((DIALOGUE_TERMINATOR,))
        )


@dataclass(frozen=True, slots=True)
class PointerSite:
    """Describe one proven little-endian pointer to a source record.

    Attributes:
        offset: Payload offset of the two-byte pointer field.
        base_offset: Payload address represented by pointer value zero.
        source_offset: Guarded source-record payload address.
        purpose: Human-readable pointer-table or call-site description.
    """

    offset: int
    base_offset: int
    source_offset: int
    purpose: str

    def __post_init__(self) -> None:
        """Validate offsets and the source pointer's 16-bit range."""

        if self.offset < 0:
            raise ValueError("pointer offset must not be negative")
        if not self.purpose:
            raise ValueError("pointer purpose must not be empty")
        self.encode_target(self.source_offset)

    def encode_target(self, target_offset: int) -> bytes:
        """Encode one payload target relative to the proven pointer base.

        Args:
            target_offset: Payload address that the pointer must reference.

        Returns:
            Two-byte little-endian pointer value.

        Raises:
            ValueError: If the target is outside the unsigned 16-bit window.
        """

        value = target_offset - self.base_offset
        if not 0 <= value <= 0xFFFF:
            raise ValueError("pointer target is outside its 16-bit window")
        return value.to_bytes(2, "little")

    def to_payload_patch(self, destination_offset: int) -> PayloadPatch:
        """Return a guarded update from source to destination.

        Args:
            destination_offset: Proven relocation target in payload space.

        Returns:
            Same-size pointer patch with exact old and new values.
        """

        return PayloadPatch(
            offset=self.offset,
            expected=self.encode_target(self.source_offset),
            replacement=self.encode_target(destination_offset),
            label=f"{self.purpose} relocation pointer",
        )


@dataclass(frozen=True, slots=True)
class RelocationArea:
    """Describe exact owned bytes inside an already loaded resource.

    Attributes:
        offset: First payload byte available for the relocated record.
        expected: Exact source bytes owned by the relocation area.
        resource_start: Inclusive start of the proven loaded resource.
        resource_end: Exclusive end of the proven loaded resource.
        alignment: Required destination alignment in bytes.
        purpose: Human-readable ownership evidence.
    """

    offset: int
    expected: bytes
    resource_start: int
    resource_end: int
    alignment: int
    purpose: str

    def __post_init__(self) -> None:
        """Validate capacity, alignment, and loaded-resource containment."""

        if not self.expected:
            raise ValueError("relocation area must have positive capacity")
        if self.resource_start < 0:
            raise ValueError("resource start must not be negative")
        if self.resource_end <= self.resource_start:
            raise ValueError("resource end must follow its start")
        if self.alignment <= 0 or self.offset % self.alignment:
            raise ValueError("relocation area violates its alignment")
        if self.offset < self.resource_start:
            raise ValueError("relocation area begins before its resource")
        if self.end_offset > self.resource_end:
            raise ValueError("relocation area extends beyond loaded resource")
        if not self.purpose:
            raise ValueError("relocation ownership purpose must not be empty")

    @property
    def end_offset(self) -> int:
        """Return the exclusive destination-area end."""

        return self.offset + len(self.expected)


@dataclass(frozen=True, slots=True)
class DialogueRelocationPlan:
    """Build guarded patches for one explicitly mapped dialogue relocation.

    Attributes:
        source_offset: Payload address of the original record marker.
        source_record: Exact original marker-through-terminator bytes.
        replacement_record: Compiled stock-renderer record.
        area: Exact owned destination bytes inside the loaded resource.
        pointers: Every proven pointer that can reach the original record.
        purpose: Human-readable translation occurrence.
    """

    source_offset: int
    source_record: bytes
    replacement_record: bytes
    area: RelocationArea
    pointers: tuple[PointerSite, ...]
    purpose: str

    def __post_init__(self) -> None:
        """Reject incomplete ownership, reachability, and size evidence."""

        if not self.purpose:
            raise ValueError("relocation purpose must not be empty")
        for label, record in (
            ("source", self.source_record),
            ("replacement", self.replacement_record),
        ):
            if not record.startswith(DIALOGUE_MARKER):
                raise ValueError(f"{label} record is missing its marker")
            if not record.endswith(bytes((DIALOGUE_TERMINATOR,))):
                raise ValueError(f"{label} record is missing its terminator")
        if not self.pointers:
            raise ValueError("relocation requires at least one proven pointer")
        if len(self.replacement_record) > len(self.area.expected):
            raise ValueError("relocated record exceeds destination capacity")
        source_end = self.source_offset + len(self.source_record)
        if self.source_offset < self.area.resource_start:
            raise ValueError("source record begins before loaded resource")
        if source_end > self.area.resource_end:
            raise ValueError("source record extends beyond loaded resource")
        if self._overlaps(
            self.source_offset,
            source_end,
            self.area.offset,
            self.area.end_offset,
        ):
            raise ValueError("source record overlaps relocation area")
        prior_pointer_ranges: list[tuple[int, int]] = []
        for pointer in self.pointers:
            if pointer.source_offset != self.source_offset:
                raise ValueError("pointer does not target the source record")
            pointer.encode_target(self.area.offset)
            pointer_start = pointer.offset
            pointer_end = pointer.offset + 2
            if self._overlaps(
                pointer_start,
                pointer_end,
                self.source_offset,
                source_end,
            ):
                raise ValueError("pointer overlaps guarded source record")
            if self._overlaps(
                pointer_start,
                pointer_end,
                self.area.offset,
                self.area.end_offset,
            ):
                raise ValueError("pointer overlaps relocation area")
            if any(
                self._overlaps(
                    pointer_start,
                    pointer_end,
                    prior_start,
                    prior_end,
                )
                for prior_start, prior_end in prior_pointer_ranges
            ):
                raise ValueError("mapped pointer fields overlap")
            prior_pointer_ranges.append((pointer_start, pointer_end))

    @staticmethod
    def _overlaps(
        first_start: int,
        first_end: int,
        second_start: int,
        second_end: int,
    ) -> bool:
        """Return whether two half-open ranges overlap."""

        return first_start < second_end and second_start < first_end

    def to_payload_patches(self) -> tuple[PayloadPatch, ...]:
        """Return source guard, pointer updates, and destination patch.

        Returns:
            Ordered same-size patches. The source guard is a no-op that proves
            the original record identity without erasing it. Unused bytes in
            the owned destination area retain their exact source values.
        """

        source_guard = PayloadPatch(
            offset=self.source_offset,
            expected=self.source_record,
            replacement=self.source_record,
            label=f"{self.purpose} source record guard",
        )
        pointer_patches = tuple(
            pointer.to_payload_patch(self.area.offset)
            for pointer in self.pointers
        )
        destination = PayloadPatch(
            offset=self.area.offset,
            expected=self.area.expected,
            replacement=(
                self.replacement_record
                + self.area.expected[len(self.replacement_record):]
            ),
            label=f"{self.purpose} relocated record",
        )
        return (source_guard,) + pointer_patches + (destination,)


def find_u16_pointer_candidates(
    data: bytes,
    target_offset: int,
    base_offset: int,
    search_start: int,
    search_end: int,
    *,
    alignment: int = 1,
) -> tuple[int, ...]:
    """Find candidate little-endian references in a bounded range.

    Args:
        data: Complete payload or another address-compatible byte sequence.
        target_offset: Payload target whose encoded value is sought.
        base_offset: Payload address represented by pointer value zero.
        search_start: Inclusive search address.
        search_end: Exclusive search address.
        alignment: Candidate-field alignment relative to ``search_start``.

    Returns:
        Candidate pointer-field offsets in ascending order.

    Raises:
        ValueError: If bounds, alignment, or the target window are invalid.

    Notes:
        A byte match is not proof of a pointer. Callers must confirm table
        structure, runtime reachability, and every alias before creating a
        ``PointerSite``.
    """

    if alignment <= 0:
        raise ValueError("pointer search alignment must be positive")
    if not 0 <= search_start <= search_end <= len(data):
        raise ValueError("pointer search bounds are outside the data")
    encoded_value = target_offset - base_offset
    if not 0 <= encoded_value <= 0xFFFF:
        raise ValueError("candidate target is outside the 16-bit window")
    needle = encoded_value.to_bytes(2, "little")
    return tuple(
        offset
        for offset in range(search_start, search_end - 1)
        if (offset - search_start) % alignment == 0
        and data[offset:offset + 2] == needle
    )
