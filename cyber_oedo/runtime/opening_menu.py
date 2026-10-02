"""Definitive Edition opening-menu presentation and CD-DA music hooks.

The stock startup menu is one command stream at payload $1B22-$1D6C.  The
redesigned stream deliberately terminates early and reclaims its own old tail
for small HuC6280 wrappers.  This is therefore not an arbitrary zero-filled
code cave: the replacement stream itself makes the reclaimed bytes
unreachable to the presentation parser.

Menu-selection semantics are preserved.  The three stock jump-table targets
remain the actual NEW GAME / LOAD / MEMORY handlers; the jump table is only
redirected through wrappers that pause menu CD-DA before entering them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch

MENU_STREAM_OFFSET = 0x00001B22
MENU_STREAM_END = 0x00001D6D
MENU_STREAM_BYTES = MENU_STREAM_END - MENU_STREAM_OFFSET
MENU_STREAM_SOURCE_SHA256 = (
    "45cee4c3513b3efbf8188a46e0f24a810d5d1b49cb84784ef6d9f9e17589321d"
)

# This startup module maps payload offset $1800 to CPU $4000.
STARTUP_CPU_BIAS = 0x2800

MENU_ENTRY_HOOK_OFFSET = 0x000019F1
MENU_ENTRY_HOOK_EXPECTED = bytes.fromhex("20 58 40")
MENU_SELECTION_JUMP_TABLE_OFFSET = 0x00001A1E
MENU_SELECTION_JUMP_TABLE_EXPECTED = bytes.fromhex("24 42 49 42 9D 42")

# Reclaimed from the old menu command stream after the new $FF terminator.
MENU_CAVE_OFFSET = 0x00001BF0
MENU_CAVE_CPU = MENU_CAVE_OFFSET + STARTUP_CPU_BIAS

STOCK_MENU_SETUP_CPU = 0x4058
STOCK_MENU_HANDLERS = (0x4224, 0x4249, 0x429D)
SYSTEM_CD_PLAY = 0xE012
SYSTEM_CD_PAUSE = 0xE018

DEFAULT_MENU_AUDIO_TRACK = 3
CUSTOM_THEME_AUDIO_TRACK = 1


class OpeningMenuError(ValueError):
    pass


def _sjis_fullwidth(text: str) -> bytes:
    try:
        return text.encode("shift_jis")
    except UnicodeEncodeError as error:
        raise OpeningMenuError(f"menu text is not Shift-JIS encodable: {text!r}") from error


def _record(opcode: int, x: int, y: int, text: bytes) -> bytes:
    if opcode not in (0, 1, 2):
        raise OpeningMenuError("startup menu record opcode must be 0, 1, or 2")
    if not 0 <= x <= 0xFF or not 0 <= y <= 0xFF:
        raise OpeningMenuError("startup menu coordinates must fit one byte")
    if b"\x00" in text:
        raise OpeningMenuError("startup menu text may not contain NUL")
    return bytes((opcode, x, y)) + text + b"\x00"


def build_definitive_menu_stream() -> bytes:
    """Return the compact cyber-police terminal menu command stream.

    The selectable rows remain at Y=$0A/$0E/$12 to preserve the stock cursor
    movement contract.
    """

    rows = (
        _record(0, 6, 10, "▼".encode("shift_jis")),
        _record(2, 7, 2, b"OEDO CYBER POLICE"),
        _record(2, 5, 4, b"SECURE ACCESS TERMINAL"),
        _record(2, 5, 6, b"----------------------"),
        _record(0, 8, 10, _sjis_fullwidth("ＮＥＷＧＡＭＥ")),
        _record(0, 8, 14, _sjis_fullwidth("ＣＯＮＴＩＮＵＥ")),
        _record(0, 8, 18, _sjis_fullwidth("ＭＥＭＯＲＹ")),
        _record(2, 8, 22, b"BUTTON I: SELECT"),
        _record(2, 4, 25, b"(C) 1991 NCS / MADHOUSE"),
        b"\xFF",
    )
    stream = b"".join(rows)
    if len(stream) >= MENU_CAVE_OFFSET - MENU_STREAM_OFFSET:
        raise OpeningMenuError("redesigned menu reaches into its reclaimed code cave")
    return stream


@dataclass(frozen=True, slots=True)
class OpeningMenuLayout:
    audio_track: int
    stream: bytes
    cave: bytes
    menu_entry_cpu: int
    stop_wrapper_cpus: tuple[int, int, int]


class _Assembler:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()

    @property
    def cpu(self) -> int:
        return self.origin + len(self.code)

    def emit(self, *values: int) -> None:
        if any(not 0 <= value <= 0xFF for value in values):
            raise OpeningMenuError("assembly byte outside 00-FF")
        self.code.extend(values)

    def jsr(self, address: int) -> None:
        self.emit(0x20, address & 0xFF, address >> 8)

    def jmp(self, address: int) -> None:
        self.emit(0x4C, address & 0xFF, address >> 8)

    def lda_imm(self, value: int) -> None:
        self.emit(0xA9, value)

    def sta_zp(self, address: int) -> None:
        self.emit(0x85, address)


def _bcd_track(track: int) -> int:
    if not 1 <= track <= 99:
        raise OpeningMenuError("CD-DA track number must be 1..99")
    return ((track // 10) << 4) | (track % 10)


def build_opening_menu_layout(
    *,
    audio_track: int = DEFAULT_MENU_AUDIO_TRACK,
) -> OpeningMenuLayout:
    """Assemble menu music entry plus three pause-and-dispatch wrappers."""

    stream = build_definitive_menu_stream()
    a = _Assembler(MENU_CAVE_CPU)

    menu_entry_cpu = a.cpu
    a.jsr(STOCK_MENU_SETUP_CPU)
    # CD_PLAY whole-track mode: AL=BCD track, BH=$80, DH bit0=loop.
    a.lda_imm(_bcd_track(audio_track))
    a.sta_zp(0xF8)
    a.lda_imm(0x80)
    a.sta_zp(0xFB)
    a.lda_imm(0x01)
    a.sta_zp(0xFF)
    a.jsr(SYSTEM_CD_PLAY)
    a.emit(0x60)  # RTS

    wrappers: list[int] = []
    for stock_handler in STOCK_MENU_HANDLERS:
        wrappers.append(a.cpu)
        a.jsr(SYSTEM_CD_PAUSE)
        a.jmp(stock_handler)

    cave = bytes(a.code)
    if MENU_CAVE_OFFSET + len(cave) > MENU_STREAM_END:
        raise OpeningMenuError("opening-menu wrapper code exceeds reclaimed stream tail")

    return OpeningMenuLayout(
        audio_track=audio_track,
        stream=stream,
        cave=cave,
        menu_entry_cpu=menu_entry_cpu,
        stop_wrapper_cpus=tuple(wrappers),  # type: ignore[arg-type]
    )


def _menu_region_replacement(layout: OpeningMenuLayout) -> bytes:
    replacement = bytearray(MENU_STREAM_BYTES)
    replacement[: len(layout.stream)] = layout.stream
    cave_at = MENU_CAVE_OFFSET - MENU_STREAM_OFFSET
    replacement[cave_at : cave_at + len(layout.cave)] = layout.cave
    return bytes(replacement)


def build_opening_menu_patches(
    payload: bytes,
    *,
    audio_track: int = DEFAULT_MENU_AUDIO_TRACK,
) -> tuple[PayloadPatch, ...]:
    """Return guarded menu redesign/music patches for an authenticated payload."""

    source_region = payload[MENU_STREAM_OFFSET:MENU_STREAM_END]
    if len(source_region) != MENU_STREAM_BYTES:
        raise OpeningMenuError("payload is too short for startup menu")
    if hashlib.sha256(source_region).hexdigest() != MENU_STREAM_SOURCE_SHA256:
        raise OpeningMenuError("startup menu stream failed its SHA-256 source guard")
    if (
        payload[MENU_ENTRY_HOOK_OFFSET : MENU_ENTRY_HOOK_OFFSET + 3]
        != MENU_ENTRY_HOOK_EXPECTED
    ):
        raise OpeningMenuError("startup menu entry hook source guard mismatch")
    if (
        payload[
            MENU_SELECTION_JUMP_TABLE_OFFSET :
            MENU_SELECTION_JUMP_TABLE_OFFSET + len(MENU_SELECTION_JUMP_TABLE_EXPECTED)
        ]
        != MENU_SELECTION_JUMP_TABLE_EXPECTED
    ):
        raise OpeningMenuError("startup menu selection jump table source guard mismatch")

    layout = build_opening_menu_layout(audio_track=audio_track)
    jump_table = b"".join(
        address.to_bytes(2, "little") for address in layout.stop_wrapper_cpus
    )
    return (
        PayloadPatch(
            offset=MENU_STREAM_OFFSET,
            expected=source_region,
            replacement=_menu_region_replacement(layout),
            label="Definitive Edition cyber-police opening menu and reclaimed code cave",
        ),
        PayloadPatch(
            offset=MENU_ENTRY_HOOK_OFFSET,
            expected=MENU_ENTRY_HOOK_EXPECTED,
            replacement=bytes(
                (0x20, layout.menu_entry_cpu & 0xFF, layout.menu_entry_cpu >> 8)
            ),
            label="Definitive Edition opening-menu CD-DA start hook",
        ),
        PayloadPatch(
            offset=MENU_SELECTION_JUMP_TABLE_OFFSET,
            expected=MENU_SELECTION_JUMP_TABLE_EXPECTED,
            replacement=jump_table,
            label="Definitive Edition opening-menu CD-DA stop wrappers",
        ),
    )
