"""Source-guarded Mission 0 Card-RAM portrait read-through benchmark.

The stock portrait loader has already decoded the portrait LBA into $FC/$FE/$FD
and the VRAM word destination into $343B/$343C before JSR $E009 at $8405.
This benchmark redirects only that call to a cave in the same Mission 0 B
overlay.

On a cache miss the cave maps Super System Card banks $68/$69 contiguously at
$A000/$C000, uses the ordinary local-memory CD_READ mode to fetch all five
portrait sectors, tags the cached LBA just past those sectors, and copies the
observed $2020 bytes to the VDC with TIA.  On a hit it performs only the TIA
copy.  The stock post-load path at $840B remains untouched.

The cave is still benchmark-only because zero-filled storage ownership and
broad portrait-route runtime coverage have not been release-certified.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.dialogue_load_architecture import MISSION0_B_PAYLOAD_BASE

PORTRAIT_CD_READ_CPU = 0x8405
PORTRAIT_CD_READ_OFFSET = MISSION0_B_PAYLOAD_BASE + PORTRAIT_CD_READ_CPU
PORTRAIT_CD_READ_EXPECTED = bytes.fromhex("20 09 E0")

PORTRAIT_CACHE_CAVE_CPU = 0x4CA0
PORTRAIT_CACHE_CAVE_OFFSET = MISSION0_B_PAYLOAD_BASE + PORTRAIT_CACHE_CAVE_CPU

PORTRAIT_BANK0 = 0x68
PORTRAIT_BANK1 = 0x69
PORTRAIT_LOCAL_ADDRESS = 0xA000
PORTRAIT_SECTORS = 5
PORTRAIT_TRANSFER_BYTES = 0x2020
PORTRAIT_TAG_ADDRESS = 0xC800
PORTRAIT_TAG_MAGIC = 0xA5


class _Assembler:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.branches: list[tuple[int, str]] = []

    def emit(self, *values: int) -> None:
        self.code.extend(values)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def branch(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0)
        self.branches.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand_index, label in self.branches:
            target = self.labels[label]
            after = operand_index + 1
            delta = target - after
            if not -128 <= delta <= 127:
                raise ValueError(f"branch to {label} is out of range")
            self.code[operand_index] = delta & 0xFF
        return bytes(self.code)


def build_portrait_cache_cave() -> bytes:
    a = _Assembler()

    # Preserve MPR0/MPR5/MPR6.
    a.emit(0x43, 0x01, 0x48)
    a.emit(0x43, 0x20, 0x48)
    a.emit(0x43, 0x40, 0x48)

    # Map two consecutive Super System Card banks at $A000-$DFFF.
    a.emit(0xA9, PORTRAIT_BANK0, 0x53, 0x20)
    a.emit(0xA9, PORTRAIT_BANK1, 0x53, 0x40)

    # Fail closed unless the valid byte and all three LBA bytes match.
    a.emit(0xAD, 0x03, 0xC8, 0xC9, PORTRAIT_TAG_MAGIC)
    a.branch(0xD0, "miss")
    for address, zp in ((0xC800, 0xFC), (0xC801, 0xFE), (0xC802, 0xFD)):
        a.emit(0xAD, address & 0xFF, address >> 8, 0xC5, zp)
        a.branch(0xD0, "miss")
    a.branch(0x80, "copy")

    a.label("miss")
    # Local CD_READ: 5 sectors -> $A000, spanning banks $68/$69.
    a.emit(0xA9, PORTRAIT_SECTORS, 0x85, 0xF8)
    a.emit(0x64, 0xF9)
    a.emit(0x64, 0xFA)
    a.emit(0xA9, 0xA0, 0x85, 0xFB)
    a.emit(0xA9, 0x01, 0x85, 0xFF)
    a.label("read_retry")
    a.emit(0x20, 0x09, 0xE0)
    a.branch(0xD0, "read_retry")

    # Tag the complete cached source by the game's native three-byte LBA order.
    for address, zp in ((0xC800, 0xFC), (0xC801, 0xFE), (0xC802, 0xFD)):
        a.emit(0xA5, zp, 0x8D, address & 0xFF, address >> 8)
    a.emit(0xA9, PORTRAIT_TAG_MAGIC, 0x8D, 0x03, 0xC8)

    a.label("copy")
    # Map hardware I/O at MPR0, set VDC MAWR from the stock destination,
    # select VWR, and copy exactly the observed 0x2020 bytes.
    a.emit(0xA9, 0xFF, 0x53, 0x01)
    a.emit(0x03, 0x00)
    a.emit(0xAD, 0x3B, 0x34, 0x8D, 0x02, 0x00)
    a.emit(0xAD, 0x3C, 0x34, 0x8D, 0x03, 0x00)
    a.emit(0x03, 0x02)
    a.emit(
        0xE3,
        0x00, 0xA0,
        0x02, 0x00,
        PORTRAIT_TRANSFER_BYTES & 0xFF,
        (PORTRAIT_TRANSFER_BYTES >> 8) & 0xFF,
    )

    # Restore mappings in reverse order and report BIOS-style success A=0.
    a.emit(0x68, 0x53, 0x40)
    a.emit(0x68, 0x53, 0x20)
    a.emit(0x68, 0x53, 0x01)
    a.emit(0xA9, 0x00, 0x60)
    return a.finish()


PORTRAIT_CACHE_CAVE_REPLACEMENT = build_portrait_cache_cave()
PORTRAIT_CACHE_CAVE_EXPECTED = bytes(len(PORTRAIT_CACHE_CAVE_REPLACEMENT))
PORTRAIT_CD_READ_REPLACEMENT = bytes(
    (0x20, PORTRAIT_CACHE_CAVE_CPU & 0xFF, PORTRAIT_CACHE_CAVE_CPU >> 8)
)


@dataclass(frozen=True, slots=True)
class PortraitCacheBenchmark:
    patches: tuple[PayloadPatch, ...]

    @property
    def changed_bytes(self) -> int:
        return sum(
            before != after
            for patch in self.patches
            for before, after in zip(patch.expected, patch.replacement, strict=True)
        )


def build_portrait_cache_benchmark() -> PortraitCacheBenchmark:
    return PortraitCacheBenchmark(
        patches=(
            PayloadPatch(
                offset=PORTRAIT_CD_READ_OFFSET,
                expected=PORTRAIT_CD_READ_EXPECTED,
                replacement=PORTRAIT_CD_READ_REPLACEMENT,
                label="Mission 0 benchmark: redirect portrait CD_READ through Card-RAM cache",
            ),
            PayloadPatch(
                offset=PORTRAIT_CACHE_CAVE_OFFSET,
                expected=PORTRAIT_CACHE_CAVE_EXPECTED,
                replacement=PORTRAIT_CACHE_CAVE_REPLACEMENT,
                label="Mission 0 benchmark: install Card-RAM portrait read-through cave",
            ),
        )
    )
