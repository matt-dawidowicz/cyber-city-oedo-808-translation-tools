"""Guarded pointer and owned-storage relocation models."""

from __future__ import annotations

from dataclasses import dataclass
from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.text.layout import (
    DIALOGUE_MARKER,
    DIALOGUE_TERMINATOR,
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
        if not 0 <= value <= 65535:
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
            self.source_offset, source_end, self.area.offset, self.area.end_offset
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
                pointer_start, pointer_end, self.source_offset, source_end
            ):
                raise ValueError("pointer overlaps guarded source record")
            if self._overlaps(
                pointer_start, pointer_end, self.area.offset, self.area.end_offset
            ):
                raise ValueError("pointer overlaps relocation area")
            if any(
                (
                    self._overlaps(pointer_start, pointer_end, prior_start, prior_end)
                    for prior_start, prior_end in prior_pointer_ranges
                )
            ):
                raise ValueError("mapped pointer fields overlap")
            prior_pointer_ranges.append((pointer_start, pointer_end))

    @staticmethod
    def _overlaps(
        first_start: int, first_end: int, second_start: int, second_end: int
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
            (pointer.to_payload_patch(self.area.offset) for pointer in self.pointers)
        )
        destination = PayloadPatch(
            offset=self.area.offset,
            expected=self.area.expected,
            replacement=self.replacement_record
            + self.area.expected[len(self.replacement_record) :],
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
    """Find aligned byte candidates without a Python byte-by-byte scan."""

    if alignment <= 0:
        raise ValueError("pointer search alignment must be positive")
    if not 0 <= search_start <= search_end <= len(data):
        raise ValueError("pointer search bounds are outside the data")
    encoded_value = target_offset - base_offset
    if not 0 <= encoded_value <= 0xFFFF:
        raise ValueError("candidate target is outside the 16-bit window")
    needle = encoded_value.to_bytes(2, "little")
    matches: list[int] = []
    offset = data.find(needle, search_start, search_end)
    while offset >= 0:
        if (offset - search_start) % alignment == 0:
            matches.append(offset)
        offset = data.find(needle, offset + 1, search_end)
    return tuple(matches)
