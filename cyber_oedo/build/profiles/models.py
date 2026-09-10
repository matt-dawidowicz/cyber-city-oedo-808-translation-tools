"""Typed, same-size text and row-layout patch models."""

from __future__ import annotations

from dataclasses import dataclass
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch


@dataclass(frozen=True, slots=True)
class InPlaceTextPatch:
    """Describe one fullwidth Shift-JIS startup-text replacement.

    Attributes:
        offset: Byte address in the extracted Track 2 payload.
        source_text: Exact decoded text expected at the address.
        english: Printable ASCII wording converted to fullwidth characters.
        purpose: Human-readable location and intent for reports.
        wrap_width: Optional fullwidth-cell width used to pad word-wrapped
            lines before encoding.

    Notes:
        ``english`` may be shorter than ``source_text`` and is right-padded
        with fullwidth spaces. It may never be longer.
    """
    offset: int
    source_text: str
    english: str
    purpose: str
    wrap_width: int | None = None

    @property
    def formatted_english(self) -> str:
        """Return ASCII English with optional cell-aware word wrapping.

        Returns:
            Original English when ``wrap_width`` is ``None``. Otherwise,
            returns lines flattened into one string with every non-final line
            padded to ``wrap_width`` cells.

        Raises:
            ValueError: If the configured width or wording cannot be wrapped.

        Notes:
            Padding relies on the game's automatic fixed-cell wrap. It adds no
            control bytes and does not change renderer behavior.
        """
        if self.wrap_width is None:
            return self.english
        return wrap_ascii_text(self.english, self.wrap_width)

    @property
    def replacement_text(self) -> str:
        """Return fullwidth English padded to the source character count.

        Returns:
            Fullwidth Shift-JIS text with exactly ``len(source_text)`` Unicode
            characters.

        Raises:
            ValueError: If the English contains non-ASCII text or exceeds the
                source character count after conversion.
        """
        replacement = ascii_to_fullwidth(self.formatted_english)
        available = len(self.source_text)
        if len(replacement) > available:
            raise ValueError(f'{self.purpose}: English uses {len(replacement)} characters; capacity is {available}')
        return replacement + '\u3000' * (available - len(replacement))

    def to_payload_patch(self) -> PayloadPatch:
        """Encode and validate this text patch for the raw-sector layer.

        Returns:
            A same-size ``PayloadPatch`` using Shift-JIS source and replacement
            bytes.

        Raises:
            UnicodeEncodeError: If source or replacement text is not encodable
                as Shift-JIS.
            ValueError: If encoded byte lengths differ.
        """
        expected = self.source_text.encode('shift_jis')
        replacement = self.replacement_text.encode('shift_jis')
        if len(expected) != len(replacement):
            raise ValueError(f'{self.purpose}: Shift-JIS byte lengths differ ({len(expected)} != {len(replacement)})')
        return PayloadPatch(offset=self.offset, expected=expected, replacement=replacement, label=self.purpose)


@dataclass(frozen=True, slots=True)
class InformationScreenLine:
    """Describe one row-addressed Media Mix information-screen record.

    The game stores each visible line as a three-byte ``00 01 RR`` row command
    followed immediately by a null-terminated, fullwidth Shift-JIS string.
    ``RR`` addresses an 8-pixel tile row even though the BIOS glyphs are
    16 pixels tall. The Japanese data places most body lines on consecutive
    rows, which makes adjacent glyphs overlap vertically. This model keeps the
    text and row edits together so a translator cannot accidentally update one
    without documenting the other.

    Attributes:
        screen: Stable page identifier used by tests and build reports.
        text_offset: Payload byte offset of the first Shift-JIS text byte.
        source_row: Exact row byte expected in the original ``00 01 RR``
            command.
        source_text: Exact decoded, null-terminated text payload expected at
            ``text_offset``. The terminator itself is not replaced.
        english: Printable ASCII replacement. An empty string intentionally
            clears the source line with fullwidth spaces.
        purpose: Human-readable role for diagnostics and the build manifest.
        target_row: Row used by the English layout. ``None`` preserves
            ``source_row``.

    Side Effects:
        Instances are immutable descriptions. Converting one to payload
        patches does not modify a file.

    Failure Conditions:
        Construction rejects offsets that cannot have a preceding command and
        row values outside the five-bit, 32-row tilemap coordinate range.
        Text conversion can also fail under ``InPlaceTextPatch`` constraints.

    Design Decisions:
        Cleared source lines are moved to ``INFORMATION_HIDDEN_ROW``. That row
        is outside the visible 30-row field but keeps both tile rows of a
        16-pixel blank glyph inside the 32-row background map. This avoids
        changing record lengths, terminators, or the page interpreter.
        The interpreter draws records in storage order, so visible target rows
        must also increase in tuple order. Visible body lines use a common
        three-cell left margin, and wording is shortened when necessary to fit
        one source record. Moving a late decorative record upward would make
        its line appear after lower lines.
    """
    screen: str
    text_offset: int
    source_row: int
    source_text: str
    english: str
    purpose: str
    target_row: int | None = None

    def __post_init__(self) -> None:
        """Validate coordinates before they can enter a build profile.

        Raises:
            ValueError: If the text does not immediately follow a three-byte
                row command or either row is outside ``0x00`` through
                ``0x1F``.
        """
        if self.text_offset < 3:
            raise ValueError(f'{self.purpose}: text offset has no preceding row command')
        if not 0 <= self.source_row <= 31:
            raise ValueError(f'{self.purpose}: invalid source row {self.source_row:#x}')
        if not 0 <= self.display_row <= 31:
            raise ValueError(f'{self.purpose}: invalid target row {self.display_row:#x}')

    @property
    def command_offset(self) -> int:
        """Return the payload offset of the line's ``00 01 RR`` command."""
        return self.text_offset - 3

    @property
    def display_row(self) -> int:
        """Return the source row or its explicit English-layout replacement."""
        if self.target_row is None:
            return self.source_row
        return self.target_row

    def to_text_patch(self) -> InPlaceTextPatch:
        """Return the guarded, same-size text replacement for this line."""
        return InPlaceTextPatch(offset=self.text_offset, source_text=self.source_text, english=self.english, purpose=self.purpose)

    def to_layout_patch(self) -> PayloadPatch | None:
        """Return a guarded row-command edit, or ``None`` when unchanged.

        Returns:
            A three-byte payload patch preserving the ``00 01`` opcode and
            replacing only its row operand, or ``None`` if the original row is
            already correct for the English layout.
        """
        if self.display_row == self.source_row:
            return None
        return PayloadPatch(offset=self.command_offset, expected=bytes((0, 1, self.source_row)), replacement=bytes((0, 1, self.display_row)), label=f'{self.purpose} row')


@dataclass(frozen=True, slots=True)
class OpeningProfileField:
    """Describe one field duplicated across the opening dossier banks.

    The opening stores seven criminal profiles twice. Each visible string
    immediately follows a ``00 0C RR`` command, where ``RR`` is an 8-pixel
    tile row. The two banks contain equivalent profile data at different
    addresses; one Gogul alias is shorter in the repeated copy. This model
    keeps the two guarded source strings, one English translation, and any
    layout edit together.

    Attributes:
        profile: Stable lowercase profile identifier used by tests and
            manifest labels.
        offsets: Payload offsets of the primary and repeated text strings.
        source_row: Exact row operand expected before both strings.
        source_text: Exact primary-bank Shift-JIS text.
        english: Printable ASCII replacement. An empty string clears the
            source field with fullwidth spaces.
        purpose: Concise field role for build diagnostics.
        target_row: Optional English-layout row. ``None`` preserves the source
            row.
        repeated_source_text: Exact repeated-bank text when it differs from
            ``source_text``. ``None`` means both copies must match.

    Side Effects:
        Instances are immutable. Conversion methods only allocate guarded
        patch descriptions.

    Failure Conditions:
        Construction rejects malformed copy counts, offsets that cannot have a
        preceding command, and rows outside the 32-row background map.
        Fullwidth conversion and same-size validation are delegated to
        ``InPlaceTextPatch``.

    Design Decisions:
        Both copies are mandatory so later navigation cannot reveal an
        untranslated duplicate. Japanese name lines are cleared offscreen and
        the existing romanized line is moved from row 5 to row 4. This removes
        the original one-row overlap without relocating records or altering
        portrait data.
    """
    profile: str
    offsets: tuple[int, int]
    source_row: int
    source_text: str
    english: str
    purpose: str
    target_row: int | None = None
    repeated_source_text: str | None = None

    def __post_init__(self) -> None:
        """Validate copy addresses and source/target row coordinates.

        Raises:
            ValueError: If the field lacks exactly two usable offsets or a row
                falls outside ``0x00`` through ``0x1F``.
        """
        if len(self.offsets) != 2:
            raise ValueError(f'{self.profile} {self.purpose}: expected two copies')
        if any((offset < 3 for offset in self.offsets)):
            raise ValueError(f'{self.profile} {self.purpose}: invalid text offset')
        if not 0 <= self.source_row <= 31:
            raise ValueError(f'{self.profile} {self.purpose}: invalid source row')
        if not 0 <= self.display_row <= 31:
            raise ValueError(f'{self.profile} {self.purpose}: invalid target row')

    @property
    def display_row(self) -> int:
        """Return the source row or its explicit English-layout replacement."""
        if self.target_row is None:
            return self.source_row
        return self.target_row

    def source_for_copy(self, copy_index: int) -> str:
        """Return the guarded source text for one dossier-bank copy.

        Args:
            copy_index: Zero for the primary bank or one for the repeated bank.

        Returns:
            ``source_text`` except for a declared repeated-bank variant.

        Raises:
            IndexError: If ``copy_index`` is not zero or one.
        """
        if copy_index not in (0, 1):
            raise IndexError('opening profile copy index must be zero or one')
        if copy_index == 1 and self.repeated_source_text is not None:
            return self.repeated_source_text
        return self.source_text

    def to_text_patches(self) -> tuple[InPlaceTextPatch, InPlaceTextPatch]:
        """Return same-size fullwidth patches for both dossier copies."""
        copy_labels = ('primary', 'repeated')
        return tuple((InPlaceTextPatch(offset=offset, source_text=self.source_for_copy(copy_index), english=self.english, purpose=f'opening profile {self.profile} {self.purpose} ({copy_labels[copy_index]})') for copy_index, offset in enumerate(self.offsets)))

    def to_layout_patches(self) -> tuple[PayloadPatch, ...]:
        """Return guarded row-command edits for both copies when required.

        Returns:
            Two three-byte patches when ``display_row`` differs from
            ``source_row``; otherwise an empty tuple.

        Design Decisions:
            The command prefix ``00 0C`` is preserved byte-for-byte. Only the
            row operand changes, keeping the dossier interpreter and null-
            terminated text structure intact.
        """
        if self.display_row == self.source_row:
            return ()
        return tuple((PayloadPatch(offset=offset - 3, expected=bytes((0, 12, self.source_row)), replacement=bytes((0, 12, self.display_row)), label=f'opening profile {self.profile} {self.purpose} copy {copy_index + 1} row') for copy_index, offset in enumerate(self.offsets)))


def wrap_ascii_text(text: str, width: int) -> str:
    """Flatten word-wrapped ASCII into fixed-width display cells.

    The original renderer advances automatically after ``width`` fullwidth
    cells. This function pads each non-final line to that boundary, making the
    existing character wrap occur between words without inserting an unknown
    dialogue control.

    Args:
        text: Single-spaced printable ASCII wording without leading or trailing
            whitespace.
        width: Positive number of fullwidth display cells per rendered line.

    Returns:
        ASCII text whose non-final visual lines are right-padded to ``width``.
        No newline or dialogue-control bytes are introduced.

    Raises:
        ValueError: If ``width`` is not positive, text spacing is not
            canonical, or a word is wider than one line.

    Design Decisions:
        This formatter is intentionally limited to the observed fixed-cell
        path. Longer accurate English belongs in mapped relocated records with
        explicit page breaks.
    """
    if width <= 0:
        raise ValueError('wrap width must be positive')
    words = text.split(' ')
    if not text or text.strip() != text or any((not word for word in words)):
        raise ValueError('wrapped English must use single internal spaces')
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
        lines.append(current.ljust(width))
        current = word
    lines.append(current)
    return ''.join(lines)


def ascii_to_fullwidth(text: str) -> str:
    """Convert printable ASCII to fullwidth Unicode equivalents.

    Args:
        text: Printable ASCII text. Ordinary spaces become ideographic spaces.

    Returns:
        Fullwidth text whose characters encode as two-byte Shift-JIS glyphs.

    Raises:
        ValueError: If ``text`` contains a character outside space through
            tilde.

    Design Decisions:
        Converting every printable character keeps the game's low-byte control
        range out of the replacement and preserves two bytes per glyph. ASCII
        hyphen maps to the Shift-JIS minus glyph and apostrophe maps to the
        right single quotation mark because U+FF0D and U+FF07 are not present
        in Python's strict ``shift_jis`` codec.
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
            raise ValueError(f'unsupported non-printable ASCII character {character!r}')
    return ''.join(converted)
