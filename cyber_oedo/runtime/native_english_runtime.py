"""Source-guarded Mission 0 native-English fixed-width runtime.

This is the executable fallback/runtime foundation for the Definitive Edition.
It deliberately preserves the game's proven 3x12-cell dialogue grid. An
English segment carries one-byte glyph IDs, but the runtime packs two glyphs
into each existing 16-pixel cell. The existing cursor, three-row redraw,
scroll, pacing, BAT writer, and all low-byte dialogue controls therefore remain
stock.

The higher-quality proportional renderer is compiled separately. This fixed
8x16 path is the compatibility/debug renderer and the live path for dynamic
strings that must be generated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.text.english_dialogue_engine import (
    ENGLISH_GLYPH_BASE,
    ENGLISH_MODE_SIGNATURE,
    ENGLISH_SEGMENT_END,
    EnglishGlyphTable,
)
from cyber_oedo.text.font_atlas import GLYPH_HEIGHT, RasterizedAtlas

SYSTEM_CARD_EX_GETFNT = 0xE060
FONT_STAGE_BUFFER = 0x4C6C
RENDER_CELL_CPU = 0x5915
STORAGE_CODE_BASE = 0x20
STORAGE_CODE_CAPACITY = 0x5F  # $20-$7E inclusive.

FONT_FETCH_HOOK_CPU = 0x56C0
FONT_FETCH_HOOK_EXPECTED = bytes.fromhex("20 60 E0")
PARSER_HOOK_DELTA = 0x91
PARSER_STOCK_GLYPH_DELTA = 0x97

M0B_STREAM_READ_CPU = 0x9F11
M0B_STREAM_ADVANCE_CPU = 0x9F14
M0B_CHARACTER_DELAY_CPU = 0x8CFC
M0B_PARSER_ENTRY = 0x9543


class NativeEnglishRuntimeError(ValueError):
    pass


class _Assembler:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[str, int, str]] = []

    @property
    def address(self) -> int:
        return self.origin + len(self.code)

    def emit(self, *values: int) -> None:
        if any(not 0 <= value <= 0xFF for value in values):
            raise NativeEnglishRuntimeError("assembly byte outside 00-FF")
        self.code.extend(values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise NativeEnglishRuntimeError(f"duplicate label: {name}")
        self.labels[name] = self.address

    def immediate(self, opcode: int, value: int) -> None:
        self.emit(opcode, value)

    def zero_page(self, opcode: int, address: int) -> None:
        self.emit(opcode, address)

    def absolute(self, opcode: int, address: int) -> None:
        if not 0 <= address <= 0xFFFF:
            raise NativeEnglishRuntimeError("absolute address outside 16-bit space")
        self.emit(opcode, address & 0xFF, address >> 8)

    def branch(self, opcode: int, target: str) -> None:
        self.emit(opcode, 0)
        self.fixups.append(("relative", len(self.code) - 1, target))

    def absolute_label(self, opcode: int, target: str) -> None:
        self.emit(opcode, 0, 0)
        self.fixups.append(("absolute", len(self.code) - 2, target))

    def finish(self) -> bytes:
        for kind, position, target in self.fixups:
            if target not in self.labels:
                raise NativeEnglishRuntimeError(f"unknown label: {target}")
            address = self.labels[target]
            if kind == "absolute":
                self.code[position] = address & 0xFF
                self.code[position + 1] = address >> 8
                continue
            displacement = address - (self.origin + position + 1)
            if not -128 <= displacement <= 127:
                raise NativeEnglishRuntimeError(
                    f"branch to {target} is out of range: {displacement}"
                )
            self.code[position] = displacement & 0xFF
        return bytes(self.code)


@dataclass(frozen=True, slots=True)
class NativeOverlayLayout:
    label: str
    payload_base: int
    parser_entry: int
    code_cpu: int
    font_cpu: int
    code_fill: int
    font_fill: int

    @property
    def parser_delta(self) -> int:
        return self.parser_entry - M0B_PARSER_ENTRY

    @property
    def parser_hook_cpu(self) -> int:
        return self.parser_entry + PARSER_HOOK_DELTA

    @property
    def parser_hook_offset(self) -> int:
        return self.payload_base + self.parser_hook_cpu

    @property
    def font_hook_offset(self) -> int:
        return self.payload_base + FONT_FETCH_HOOK_CPU


MISSION0_NATIVE_LAYOUTS = (
    NativeOverlayLayout(
        "MISSION_0_A",
        payload_base=0x00074800,
        parser_entry=0x94A7,
        code_cpu=0xAA50,
        font_cpu=0xAC00,
        code_fill=0xFF,
        font_fill=0xFF,
    ),
    NativeOverlayLayout(
        "MISSION_0_B",
        payload_base=0x00131800,
        parser_entry=0x9543,
        code_cpu=0xA300,
        font_cpu=0xA800,
        code_fill=0x00,
        font_fill=0xE5,
    ),
)


@dataclass(frozen=True, slots=True)
class NativeOverlayRuntime:
    layout: NativeOverlayLayout
    code: bytes
    atlas_row_major: bytes
    labels: dict[str, int]
    glyph_count: int
    space_glyph_id: int
    question_glyph_id: int

    @property
    def glyph_hook_cpu(self) -> int:
        return self.labels["glyph_hook"]

    def __post_init__(self) -> None:
        if self.layout.code_cpu + len(self.code) > self.layout.font_cpu:
            raise NativeEnglishRuntimeError(
                f"{self.layout.label}: code overlaps font storage"
            )
        if self.glyph_count > STORAGE_CODE_CAPACITY:
            raise NativeEnglishRuntimeError(
                f"{self.layout.label}: glyph repertoire exceeds 95 storage codes"
            )


def _atlas_row_major(atlas: RasterizedAtlas) -> bytes:
    return bytes(
        atlas.glyphs[glyph_id][row]
        for row in range(GLYPH_HEIGHT)
        for glyph_id in range(len(atlas.glyphs))
    )


def _emit_runtime(
    layout: NativeOverlayLayout,
    *,
    glyph_count: int,
    space_glyph_id: int,
    question_glyph_id: int,
) -> tuple[bytes, dict[str, int]]:
    if not 0 < glyph_count <= STORAGE_CODE_CAPACITY:
        raise NativeEnglishRuntimeError("glyph count must fit $20-$7E storage codes")
    for glyph_id in (space_glyph_id, question_glyph_id):
        if not 0 <= glyph_id < glyph_count:
            raise NativeEnglishRuntimeError("special glyph ID lies outside atlas")

    stream_read = M0B_STREAM_READ_CPU + layout.parser_delta
    stream_advance = M0B_STREAM_ADVANCE_CPU + layout.parser_delta
    character_delay = M0B_CHARACTER_DELAY_CPU + layout.parser_delta
    parser_restart = layout.parser_entry
    stock_glyph_continuation = layout.parser_entry + PARSER_STOCK_GLYPH_DELTA

    assembler = _Assembler(layout.code_cpu)

    # The hook replaces the stock CMP #$80 / BEQ prefix. Detect 7D 45 only;
    # otherwise reconstruct the stock <=$80 decision exactly.
    assembler.label("parser_dispatch")
    assembler.immediate(0xC9, ENGLISH_MODE_SIGNATURE[0])
    assembler.branch(0xD0, "normal_compare")
    assembler.emit(0xB2, 0x7F)  # LDA ($7F): signature byte 2.
    assembler.immediate(0xC9, ENGLISH_MODE_SIGNATURE[1])
    assembler.branch(0xD0, "restore_first_signature")
    assembler.absolute(0x20, stream_advance)
    assembler.branch(0x80, "english_left")

    assembler.label("restore_first_signature")
    assembler.immediate(0xA9, ENGLISH_MODE_SIGNATURE[0])

    assembler.label("normal_compare")
    assembler.immediate(0xC9, 0x80)
    assembler.branch(0xF0, "parser_restart")
    assembler.branch(0x90, "parser_restart")
    assembler.absolute(0x4C, stock_glyph_continuation)

    assembler.label("parser_restart")
    assembler.absolute(0x4C, parser_restart)

    # Convert a stream glyph ID ($80+index) into the compact byte persisted in
    # the stock two-byte cell ($20+index). Invalid IDs become '?'.
    assembler.label("english_left")
    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.immediate(0xC9, ENGLISH_SEGMENT_END)
    assembler.branch(0xF0, "parser_restart")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE)
    assembler.branch(0x90, "left_question")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE + glyph_count)
    assembler.branch(0xB0, "left_question")
    assembler.emit(0x38)  # SEC
    assembler.immediate(0xE9, ENGLISH_GLYPH_BASE - STORAGE_CODE_BASE)
    assembler.branch(0x80, "left_ready")

    assembler.label("left_question")
    assembler.immediate(0xA9, STORAGE_CODE_BASE + question_glyph_id)
    assembler.label("left_ready")
    assembler.zero_page(0x85, 0x03)

    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.immediate(0xC9, ENGLISH_SEGMENT_END)
    assembler.branch(0xF0, "english_odd")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE)
    assembler.branch(0x90, "right_question")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE + glyph_count)
    assembler.branch(0xB0, "right_question")
    assembler.emit(0x38)
    assembler.immediate(0xE9, ENGLISH_GLYPH_BASE - STORAGE_CODE_BASE)
    assembler.branch(0x80, "right_ready")

    assembler.label("right_question")
    assembler.immediate(0xA9, STORAGE_CODE_BASE + question_glyph_id)
    assembler.label("right_ready")
    assembler.zero_page(0x85, 0x02)
    assembler.absolute(0x20, character_delay)
    assembler.absolute(0x20, RENDER_CELL_CPU)
    assembler.branch(0x80, "english_left")

    assembler.label("english_odd")
    assembler.immediate(0xA9, STORAGE_CODE_BASE + space_glyph_id)
    assembler.zero_page(0x85, 0x02)
    assembler.absolute(0x20, character_delay)
    assembler.absolute(0x20, RENDER_CELL_CPU)
    assembler.branch(0x80, "parser_restart")

    # The stock renderer copies the persisted cell bytes into $F9/$F8 before
    # the overwritten EX_GETFNT call. Both bytes in our compact storage range
    # select the custom 8x16 compositor; every other pair jumps to the BIOS.
    assembler.label("glyph_hook")
    for zero_page in (0xF9, 0xF8):
        assembler.zero_page(0xA5, zero_page)
        assembler.immediate(0xC9, STORAGE_CODE_BASE)
        assembler.branch(0x90, "stock_glyph")
        assembler.immediate(0xC9, STORAGE_CODE_BASE + glyph_count)
        assembler.branch(0xB0, "stock_glyph")
    assembler.branch(0x80, "custom_glyph")

    assembler.label("stock_glyph")
    assembler.absolute(0x4C, SYSTEM_CARD_EX_GETFNT)

    assembler.label("custom_glyph")
    assembler.emit(0xDA)  # PHX
    assembler.emit(0x5A)  # PHY
    assembler.zero_page(0xA5, 0xF9)
    assembler.emit(0x38)
    assembler.immediate(0xE9, STORAGE_CODE_BASE)
    assembler.emit(0xAA)  # TAX
    assembler.zero_page(0xA5, 0xF8)
    assembler.emit(0x38)
    assembler.immediate(0xE9, STORAGE_CODE_BASE)
    assembler.emit(0xA8)  # TAY

    for row in range(GLYPH_HEIGHT):
        row_base = layout.font_cpu + row * glyph_count
        destination = FONT_STAGE_BUFFER + row * 2
        assembler.absolute(0xBD, row_base)
        assembler.absolute(0x8D, destination)
        assembler.absolute(0xB9, row_base)
        assembler.absolute(0x8D, destination + 1)

    assembler.emit(0x7A)  # PLY
    assembler.emit(0xFA)  # PLX
    assembler.emit(0x60)  # RTS
    return assembler.finish(), dict(assembler.labels)


def build_overlay_runtime(
    layout: NativeOverlayLayout,
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
) -> NativeOverlayRuntime:
    if atlas.characters != glyphs.characters:
        raise NativeEnglishRuntimeError(
            "atlas character order must exactly match native glyph table"
        )
    try:
        space_id = glyphs.characters.index(" ")
        question_id = glyphs.characters.index("?")
    except ValueError as error:
        raise NativeEnglishRuntimeError(
            "native glyph repertoire must contain space and '?'"
        ) from error

    code, labels = _emit_runtime(
        layout,
        glyph_count=len(glyphs.characters),
        space_glyph_id=space_id,
        question_glyph_id=question_id,
    )
    return NativeOverlayRuntime(
        layout=layout,
        code=code,
        atlas_row_major=_atlas_row_major(atlas),
        labels=labels,
        glyph_count=len(glyphs.characters),
        space_glyph_id=space_id,
        question_glyph_id=question_id,
    )


def overlay_runtime_patches(runtime: NativeOverlayRuntime) -> tuple[PayloadPatch, ...]:
    layout = runtime.layout
    return (
        PayloadPatch(
            offset=layout.parser_hook_offset,
            expected=bytes.fromhex("C9 80 F0"),
            replacement=bytes(
                (0x4C, layout.code_cpu & 0xFF, layout.code_cpu >> 8)
            ),
            label=f"{layout.label}: native-English parser trampoline",
        ),
        PayloadPatch(
            offset=layout.font_hook_offset,
            expected=FONT_FETCH_HOOK_EXPECTED,
            replacement=bytes(
                (
                    0x20,
                    runtime.glyph_hook_cpu & 0xFF,
                    runtime.glyph_hook_cpu >> 8,
                )
            ),
            label=f"{layout.label}: native-English 8x16 glyph compositor",
        ),
        PayloadPatch(
            offset=layout.payload_base + layout.code_cpu,
            expected=bytes((layout.code_fill,)) * len(runtime.code),
            replacement=runtime.code,
            label=f"{layout.label}: native-English runtime code",
        ),
        PayloadPatch(
            offset=layout.payload_base + layout.font_cpu,
            expected=bytes((layout.font_fill,)) * len(runtime.atlas_row_major),
            replacement=runtime.atlas_row_major,
            label=f"{layout.label}: native-English row-major font atlas",
        ),
    )


def build_mission0_native_runtime_patches(
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
) -> tuple[PayloadPatch, ...]:
    patches: list[PayloadPatch] = []
    for layout in MISSION0_NATIVE_LAYOUTS:
        patches.extend(
            overlay_runtime_patches(build_overlay_runtime(layout, glyphs, atlas))
        )
    return tuple(patches)
