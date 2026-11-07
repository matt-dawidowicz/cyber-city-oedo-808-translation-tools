"""Named-resource descriptor tables and the Mission 0-B resource-heap contract.

Each mission overlay embeds a table of fixed 16-byte descriptors at CPU
``$5D4B``.  The Mission 0-B lookup at ``$6E36`` walks that table, and the
loader at ``$6CCB`` (called from ``$8F9A``) installs the matching resource at
the current bump-heap pointer ``$2778/$2779``.

Statically proven loader contract (Mission 0-B, source-guarded below):

* descriptor byte 9 is read as the LBA high byte, bytes 10-11 as the LBA
  low/middle bytes, and bytes 13-14 as a 16-bit byte length.  The span byte
  (12) and length byte 15 are never read by this loader;
* the heap starts at ``$C000`` (``$40C4-$40D5``) and a load is rejected when
  ``destination + length >= $D800``, which triggers heap compaction at
  ``$9BBA`` and a retry;
* after loading, ``$420C`` copies the resource down by 16 bytes, so the first
  16 bytes are a header that is not resident, and the heap advances by
  ``length - 16``;
* compaction moves resident resources, so nothing may hold an absolute RAM
  pointer into a resource across loads.

Live MesenCE capture (``tools/mesen_named_resource_heap_probe.lua``) of the
original opening shows ``INIT`` loading at ``$C000`` and ``KURUZER`` at
``$C350`` with no compaction through frame 8,700.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from cyber_oedo.disc.game_layout import SECTOR_SIZE, TRACK2_SECTOR_COUNT, TRACK2_START_LBA

DESCRIPTOR_SIZE = 16
DESCRIPTOR_NAME_BYTES = 10
DESCRIPTOR_TABLE_CPU = 0x5D4B

MISSION0_B_MODULE_BASE = 0x00131800
MISSION0_B_DESCRIPTOR_TABLE_OFFSET = MISSION0_B_MODULE_BASE + DESCRIPTOR_TABLE_CPU
MISSION0_B_DESCRIPTOR_COUNT = 48
MISSION0_B_DESCRIPTOR_TABLE_SHA256 = (
    "502d5119fc3ab0cf1cd21bef68221f46008f4003868601ab49ca1399bfc4fb1b"
)

# Source guards for the loader contract described in the module docstring.
MISSION0_B_LOADER_GUARDS = (
    ("descriptor lookup", 0x6E36, bytes.fromhex("A5 00 48 A5 01 48 A9 4B 85 00 A9 5D 85 01")),
    ("heap bound check", 0x6D1F, bytes.fromhex("A5 01 C9 D8 D0 04 A5 00 C9 00")),
    ("header strip copy", 0x6D91, bytes.fromhex("A5 10 18 69 10 85 10")),
    ("heap base init", 0x40CE, bytes.fromhex("A9 00 8D 78 27 A9 C0 8D 79 27")),
    ("load call", 0x8F90, bytes.fromhex("AD 78 27 85 06 AD 79 27 85 07 20 CB 6C")),
)

RESOURCE_HEADER_BYTES = 16
HEAP_BASE = 0xC000
HEAP_LIMIT = 0xD800

_NAME_PATTERN = re.compile(rb"[A-Z0-9_]{2,9}")


class NamedResourceError(ValueError):
    """Raised when descriptor evidence does not match the proven contract."""


@dataclass(frozen=True, slots=True)
class NamedResourceDescriptor:
    """One 16-byte descriptor at a known payload offset."""

    name: str
    payload_offset: int
    absolute_lba: int
    span: int
    byte_length: int
    raw: bytes

    @property
    def relative_sector(self) -> int:
        return self.absolute_lba - TRACK2_START_LBA

    @property
    def resource_payload_offset(self) -> int:
        return self.relative_sector * SECTOR_SIZE

    @property
    def mutable_tail_offset(self) -> int:
        """Payload offset of descriptor bytes 9-15 (LBA, span, length)."""

        return self.payload_offset + DESCRIPTOR_NAME_BYTES - 1


def decode_descriptor(raw: bytes, payload_offset: int) -> NamedResourceDescriptor:
    """Decode one descriptor with the field layout the loader actually reads."""

    if len(raw) != DESCRIPTOR_SIZE:
        raise NamedResourceError(f"descriptor at 0x{payload_offset:08X} is not 16 bytes")
    name_field = raw[: DESCRIPTOR_NAME_BYTES - 1]
    terminator = name_field.find(b"\0")
    name = name_field if terminator < 0 else name_field[:terminator]
    if not _NAME_PATTERN.fullmatch(name) or any(name_field[len(name):]):
        raise NamedResourceError(f"descriptor at 0x{payload_offset:08X} has an invalid name")
    absolute_lba = (raw[9] << 16) | int.from_bytes(raw[10:12], "little")
    span = raw[12]
    byte_length = int.from_bytes(raw[13:16], "little")
    relative = absolute_lba - TRACK2_START_LBA
    if not 0 <= relative < TRACK2_SECTOR_COUNT:
        raise NamedResourceError(f"{name.decode()}: LBA 0x{absolute_lba:X} is outside Track 2")
    if not 0 < byte_length <= span * SECTOR_SIZE:
        raise NamedResourceError(f"{name.decode()}: length does not fit its sector span")
    return NamedResourceDescriptor(
        name=name.decode("ascii"),
        payload_offset=payload_offset,
        absolute_lba=absolute_lba,
        span=span,
        byte_length=byte_length,
        raw=bytes(raw),
    )


def verify_mission0_b_loader(payload: bytes | memoryview) -> None:
    """Fail closed unless every loader-contract instruction is unchanged."""

    for label, cpu, expected in MISSION0_B_LOADER_GUARDS:
        start = MISSION0_B_MODULE_BASE + cpu
        if bytes(payload[start : start + len(expected)]) != expected:
            raise NamedResourceError(f"Mission 0-B {label} at ${cpu:04X} differs from source")


def parse_mission0_b_descriptors(
    payload: bytes | memoryview,
) -> tuple[NamedResourceDescriptor, ...]:
    """Return the authenticated Mission 0-B descriptor table."""

    start = MISSION0_B_DESCRIPTOR_TABLE_OFFSET
    end = start + MISSION0_B_DESCRIPTOR_COUNT * DESCRIPTOR_SIZE
    table = bytes(payload[start:end])
    if hashlib.sha256(table).hexdigest() != MISSION0_B_DESCRIPTOR_TABLE_SHA256:
        raise NamedResourceError("Mission 0-B descriptor table differs from source")
    verify_mission0_b_loader(payload)
    return tuple(
        decode_descriptor(table[index : index + DESCRIPTOR_SIZE], start + index)
        for index in range(0, len(table), DESCRIPTOR_SIZE)
    )


def find_descriptor(
    descriptors: tuple[NamedResourceDescriptor, ...],
    name: str,
) -> NamedResourceDescriptor:
    matches = [row for row in descriptors if row.name == name]
    if len(matches) != 1:
        raise NamedResourceError(f"expected exactly one {name} descriptor, found {len(matches)}")
    return matches[0]


def descriptor_references(
    payload: bytes | memoryview,
    absolute_lbas: range,
) -> tuple[tuple[int, str, int], ...]:
    """Find every descriptor-shaped record anywhere in the payload naming an LBA.

    A record counts when it has a valid NUL-padded name and its span covers any
    requested sector.  This is a conservative ownership check across all
    overlays, not only Mission 0-B.
    """

    data = bytes(payload)
    hits: list[tuple[int, str, int]] = []
    wanted = set(absolute_lbas)
    for match in re.finditer(rb"(?=[A-Z0-9_]{2,9}\x00)", data):
        offset = match.start()
        raw = data[offset : offset + DESCRIPTOR_SIZE]
        if len(raw) != DESCRIPTOR_SIZE:
            continue
        try:
            row = decode_descriptor(raw, offset)
        except NamedResourceError:
            continue
        covered = range(row.absolute_lba, row.absolute_lba + max(row.span, 1))
        if wanted.intersection(covered):
            hits.append((offset, row.name, row.absolute_lba))
    return tuple(hits)


def max_resource_length(load_address: int) -> int:
    """Largest descriptor length the loader accepts at *load_address*."""

    if not HEAP_BASE <= load_address < HEAP_LIMIT:
        raise NamedResourceError(f"load address ${load_address:04X} is outside the heap")
    return HEAP_LIMIT - load_address - 1


# Load order observed in MesenCE on the opening and street route through the
# first watcher conversation (tools/mesen_named_resource_heap_probe.lua):
# INIT at $C000, KURUZER at $C350, ZAKO0001 at $C660, no compaction.
MISSION0_STREET_ROUTE = ("INIT", "KURUZER", "ZAKO0001")


def predict_heap_addresses(
    route: tuple[tuple[str, int], ...],
) -> dict[str, int]:
    """Predict load addresses for ``(name, byte_length)`` in route order.

    Models the bump heap without compaction: each resource loads at the
    pointer and advances it by ``length - 16``.  Raises if any load would
    reach the ``$D800`` bound, since relying on compaction is not proven.
    """

    address = HEAP_BASE
    addresses: dict[str, int] = {}
    for name, length in route:
        if address + length >= HEAP_LIMIT:
            raise NamedResourceError(
                f"{name}: {length} bytes at ${address:04X} reaches the ${HEAP_LIMIT:04X} heap bound"
            )
        addresses[name] = address
        address += length - RESOURCE_HEADER_BYTES
    return addresses
