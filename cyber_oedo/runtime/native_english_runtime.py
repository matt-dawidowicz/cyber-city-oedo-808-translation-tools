"""Source-guarded native-English fixed-width runtime for Mission 0-8.

English stream segments are decoded into pairs of compact glyph IDs and stored
inside the game's existing 3x12x3-byte dialogue grid. The stock cursor,
three-row redraw, scroll, pacing, BAT writer, and low-byte control handlers stay
unchanged.

Every common text overlay has the same parser/renderer contract but different
relocated parser addresses. Small overlay-local fill regions hold the native
interpreter. The 16 row tables of the 8x16 atlas may be split across multiple
fill regions; the compositor uses explicit absolute row addresses, so atlas
storage does not need to be contiguous.

This is the compatibility/dynamic-string renderer. Static dialogue may use the
build-time proportional renderer once that runtime path is certified.
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
from cyber_oedo.text.vwf_cells import (
    VWF_CARD_RAM_BASE_BANK,
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VWF_TOKEN_FIRST_MAX,
    VWF_TOKEN_FIRST_MIN,
)

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
class FontRegion:
    """One source-guarded fill region assigned to consecutive atlas rows."""

    cpu_address: int
    first_row: int
    row_count: int
    fill_byte: int

    def __post_init__(self) -> None:
        if not 0 <= self.first_row < GLYPH_HEIGHT:
            raise NativeEnglishRuntimeError("font first row is outside 0..15")
        if self.row_count <= 0 or self.first_row + self.row_count > GLYPH_HEIGHT:
            raise NativeEnglishRuntimeError("font row range is invalid")
        if not 0 <= self.fill_byte <= 0xFF:
            raise NativeEnglishRuntimeError("font fill byte is invalid")


@dataclass(frozen=True, slots=True)
class NativeOverlayLayout:
    label: str
    payload_base: int
    parser_entry: int
    code_cpu: int
    code_fill: int
    font_regions: tuple[FontRegion, ...]

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


COMMON_SPLIT_FONT = (
    FontRegion(0xC261, 0, 15, 0x00),
)

TEXT_NATIVE_LAYOUTS = (
    NativeOverlayLayout(
        "MISSION_0_A", 0x00074800, 0x94A7, 0xAA50, 0xFF,
        (FontRegion(0xAC00, 0, 16, 0xFF),),
    ),
    NativeOverlayLayout(
        "MISSION_0_B", 0x00131800, 0x9543, 0xA300, 0x00,
        (FontRegion(0xA800, 0, 16, 0xE5),),
    ),
    NativeOverlayLayout(
        "MISSION_1", 0x00CE4000, 0x95AA, 0xA3C0, 0x00,
        (FontRegion(0xA800, 0, 16, 0xE5),),
    ),
    NativeOverlayLayout(
        "MISSION_2", 0x017B3800, 0x95AE, 0xA400, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA600, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_3", 0x0222C000, 0x9580, 0xA480, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA600, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_4", 0x02B1C000, 0x950E, 0xA4A0, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA620, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_5", 0x03356800, 0x9581, 0xA500, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA680, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_6", 0x03B34000, 0x9526, 0xA500, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA680, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_7", 0x04281800, 0x94A8, 0xA500, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA680, 15, 1, 0x00),),
    ),
    NativeOverlayLayout(
        "MISSION_8", 0x04848000, 0x94A7, 0xA500, 0x00,
        COMMON_SPLIT_FONT + (FontRegion(0xA680, 15, 1, 0x00),),
    ),
)

# Compatibility name retained for callers that specifically need Mission 0.
MISSION0_NATIVE_LAYOUTS = TEXT_NATIVE_LAYOUTS[:2]


@dataclass(frozen=True, slots=True)
class NativeOverlayRuntime:
    layout: NativeOverlayLayout
    code: bytes
    font_row_bytes: tuple[bytes, ...]
    font_row_cpus: tuple[int, ...]
    labels: dict[str, int]
    glyph_count: int
    space_glyph_id: int
    question_glyph_id: int

    @property
    def glyph_hook_cpu(self) -> int:
        return self.labels["glyph_hook"]

    def __post_init__(self) -> None:
        if len(self.font_row_bytes) != GLYPH_HEIGHT:
            raise NativeEnglishRuntimeError("runtime must carry exactly 16 font rows")
        if len(self.font_row_cpus) != GLYPH_HEIGHT:
            raise NativeEnglishRuntimeError("runtime must address exactly 16 font rows")
        if self.glyph_count > STORAGE_CODE_CAPACITY:
            raise NativeEnglishRuntimeError(
                f"{self.layout.label}: glyph repertoire exceeds 95 storage codes"
            )


def _font_rows(atlas: RasterizedAtlas) -> tuple[bytes, ...]:
    return tuple(
        bytes(atlas.glyphs[glyph_id][row] for glyph_id in range(len(atlas.glyphs)))
        for row in range(GLYPH_HEIGHT)
    )


def _resolve_font_row_cpus(
    layout: NativeOverlayLayout,
    glyph_count: int,
) -> tuple[int, ...]:
    addresses: list[int | None] = [None] * GLYPH_HEIGHT
    for region in layout.font_regions:
        for relative_row in range(region.row_count):
            row = region.first_row + relative_row
            if addresses[row] is not None:
                raise NativeEnglishRuntimeError(
                    f"{layout.label}: font row {row} assigned twice"
                )
            addresses[row] = region.cpu_address + relative_row * glyph_count
    if any(address is None for address in addresses):
        raise NativeEnglishRuntimeError(f"{layout.label}: font row layout is incomplete")
    return tuple(int(address) for address in addresses)


def _emit_runtime(
    layout: NativeOverlayLayout,
    *,
    glyph_count: int,
    space_glyph_id: int,
    question_glyph_id: int,
    font_row_cpus: tuple[int, ...],
) -> tuple[bytes, dict[str, int]]:
    if not 0 < glyph_count <= STORAGE_CODE_CAPACITY:
        raise NativeEnglishRuntimeError("glyph count must fit $20-$7E storage codes")
    if len(font_row_cpus) != GLYPH_HEIGHT:
        raise NativeEnglishRuntimeError("font row address table must contain 16 rows")
    for glyph_id in (space_glyph_id, question_glyph_id):
        if not 0 <= glyph_id < glyph_count:
            raise NativeEnglishRuntimeError("special glyph ID lies outside atlas")

    stream_read = M0B_STREAM_READ_CPU + layout.parser_delta
    stream_advance = M0B_STREAM_ADVANCE_CPU + layout.parser_delta
    character_delay = M0B_CHARACTER_DELAY_CPU + layout.parser_delta
    parser_restart = layout.parser_entry
    stock_glyph_continuation = layout.parser_entry + PARSER_STOCK_GLYPH_DELTA

    assembler = _Assembler(layout.code_cpu)

    assembler.label("parser_dispatch")
    assembler.immediate(0xC9, ENGLISH_MODE_SIGNATURE[0])
    assembler.branch(0xD0, "normal_compare")
    assembler.emit(0xB2, 0x7F)  # LDA ($7F): signature byte 2.
    assembler.immediate(0xC9, ENGLISH_MODE_SIGNATURE[1])
    assembler.branch(0xF0, "fixed_signature")
    assembler.immediate(0xC9, VWF_MODE_SIGNATURE[1])
    assembler.branch(0xF0, "vwf_signature")
    assembler.branch(0x80, "restore_first_signature")

    assembler.label("fixed_signature")
    assembler.absolute(0x20, stream_advance)
    assembler.branch(0x80, "english_left")

    assembler.label("vwf_signature")
    assembler.absolute(0x20, stream_advance)
    assembler.branch(0x80, "vwf_first")

    assembler.label("restore_first_signature")
    assembler.immediate(0xA9, ENGLISH_MODE_SIGNATURE[0])

    assembler.label("normal_compare")
    assembler.immediate(0xC9, 0x80)
    assembler.branch(0xF0, "parser_restart")
    assembler.branch(0x90, "parser_restart")
    assembler.absolute(0x4C, stock_glyph_continuation)

    assembler.label("parser_restart")
    assembler.absolute(0x4C, parser_restart)

    assembler.label("vwf_first")
    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.immediate(0xC9, 0xFF)
    assembler.branch(0xF0, "vwf_end_second")
    assembler.immediate(0xC9, VWF_TOKEN_FIRST_MIN)
    assembler.branch(0x90, "parser_restart")
    assembler.immediate(0xC9, VWF_TOKEN_FIRST_MAX + 1)
    assembler.branch(0xB0, "parser_restart")
    assembler.zero_page(0x85, 0x03)
    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.zero_page(0x85, 0x02)
    assembler.absolute(0x20, character_delay)
    assembler.absolute(0x20, RENDER_CELL_CPU)
    assembler.branch(0x80, "vwf_first")

    assembler.label("vwf_end_second")
    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.immediate(0xC9, VWF_SEGMENT_END_TOKEN & 0xFF)
    assembler.branch(0x80, "parser_restart")

    assembler.label("english_left")
    assembler.absolute(0x20, stream_read)
    assembler.absolute(0x20, stream_advance)
    assembler.immediate(0xC9, ENGLISH_SEGMENT_END)
    assembler.branch(0xF0, "parser_restart")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE)
    assembler.branch(0x90, "left_question")
    assembler.immediate(0xC9, ENGLISH_GLYPH_BASE + glyph_count)
    assembler.branch(0xB0, "left_question")
    assembler.emit(0x38)
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

    assembler.label("glyph_hook")
    # VWF cells are redraw-self-identifying: first stored byte $01-$0C.
    assembler.zero_page(0xA5, 0xF9)
    assembler.immediate(0xC9, VWF_TOKEN_FIRST_MIN)
    assembler.branch(0x90, "fixed_glyph_check")
    assembler.immediate(0xC9, VWF_TOKEN_FIRST_MAX + 1)
    assembler.branch(0x90, "vwf_glyph")

    assembler.label("fixed_glyph_check")
    for zero_page in (0xF9, 0xF8):
        assembler.zero_page(0xA5, zero_page)
        assembler.immediate(0xC9, STORAGE_CODE_BASE)
        assembler.branch(0x90, "stock_glyph")
        assembler.immediate(0xC9, STORAGE_CODE_BASE + glyph_count)
        assembler.branch(0xB0, "stock_glyph")
    assembler.branch(0x80, "custom_glyph")

    assembler.label("stock_glyph")
    assembler.absolute(0x4C, SYSTEM_CARD_EX_GETFNT)

    assembler.label("vwf_glyph")
    # Token high byte selects one 8 KiB Card-RAM bank. Token low byte
    # selects one of its 256 pre-rendered 32-byte staging cells.
    assembler.emit(0x5A)  # PHY
    assembler.emit(0x43, 0x20)  # TMA #$20: preserve MPR5.
    assembler.emit(0x48)  # PHA
    assembler.zero_page(0xA5, 0x00)
    assembler.emit(0x48)
    assembler.zero_page(0xA5, 0x01)
    assembler.emit(0x48)

    assembler.zero_page(0xA5, 0xF9)
    assembler.emit(0x18)  # CLC
    assembler.immediate(0x69, VWF_CARD_RAM_BASE_BANK - VWF_TOKEN_FIRST_MIN)
    assembler.emit(0x53, 0x20)  # TAM #$20 -> map selected bank at $A000.

    assembler.zero_page(0xA5, 0xF8)
    for _ in range(5):
        assembler.emit(0x0A)  # ASL A
    assembler.zero_page(0x85, 0x00)
    assembler.zero_page(0xA5, 0xF8)
    for _ in range(3):
        assembler.emit(0x4A)  # LSR A
    assembler.emit(0x18)  # CLC
    assembler.immediate(0x69, 0xA0)
    assembler.zero_page(0x85, 0x01)

    assembler.immediate(0xA0, 0x00)  # LDY #0
    assembler.label("vwf_copy_cell")
    assembler.emit(0xB1, 0x00)  # LDA ($00),Y
    assembler.emit(0x99, FONT_STAGE_BUFFER & 0xFF, FONT_STAGE_BUFFER >> 8)  # STA abs,Y
    assembler.emit(0xC8)  # INY
    assembler.immediate(0xC0, 0x20)  # CPY #32
    assembler.branch(0xD0, "vwf_copy_cell")

    assembler.emit(0x68)  # PLA
    assembler.zero_page(0x85, 0x01)
    assembler.emit(0x68)  # PLA
    assembler.zero_page(0x85, 0x00)
    assembler.emit(0x68)  # PLA
    assembler.emit(0x53, 0x20)  # TAM #$20: restore MPR5.
    assembler.emit(0x7A)  # PLY
    assembler.emit(0x60)  # RTS

    assembler.label("custom_glyph")
    # Fixed 8x16 fallback, compacted through a row-pointer table.
    assembler.emit(0xDA)  # PHX
    assembler.emit(0x5A)  # PHY
    for scratch in (0x00, 0x01, 0x04, 0x05):
        assembler.zero_page(0xA5, scratch)
        assembler.emit(0x48)  # PHA

    assembler.zero_page(0xA5, 0xF9)
    assembler.emit(0x38)  # SEC
    assembler.immediate(0xE9, STORAGE_CODE_BASE)
    assembler.zero_page(0x85, 0x05)
    assembler.zero_page(0xA5, 0xF8)
    assembler.emit(0x38)  # SEC
    assembler.immediate(0xE9, STORAGE_CODE_BASE)
    assembler.zero_page(0x85, 0x04)

    assembler.immediate(0xA0, 0x00)  # LDY #0
    assembler.label("fixed_row_loop")
    assembler.absolute_label(0xB9, "fixed_row_table")
    assembler.emit(0x18)  # CLC
    assembler.zero_page(0x65, 0x05)
    assembler.zero_page(0x85, 0x00)
    assembler.absolute_label(0xB9, "fixed_row_table_high")
    assembler.immediate(0x69, 0x00)
    assembler.zero_page(0x85, 0x01)
    assembler.emit(0xB2, 0x00)
    assembler.absolute(0x99, FONT_STAGE_BUFFER)

    assembler.absolute_label(0xB9, "fixed_row_table")
    assembler.emit(0x18)  # CLC
    assembler.zero_page(0x65, 0x04)
    assembler.zero_page(0x85, 0x00)
    assembler.absolute_label(0xB9, "fixed_row_table_high")
    assembler.immediate(0x69, 0x00)
    assembler.zero_page(0x85, 0x01)
    assembler.emit(0xB2, 0x00)
    assembler.emit(0x99, (FONT_STAGE_BUFFER + 1) & 0xFF, (FONT_STAGE_BUFFER + 1) >> 8)

    assembler.emit(0xC8, 0xC8)
    assembler.immediate(0xC0, 0x20)
    assembler.branch(0xD0, "fixed_row_loop")

    for scratch in (0x05, 0x04, 0x01, 0x00):
        assembler.emit(0x68)
        assembler.zero_page(0x85, scratch)
    assembler.emit(0x7A)  # PLY
    assembler.emit(0xFA)  # PLX
    assembler.emit(0x60)

    assembler.label("fixed_row_table")
    assembler.labels["fixed_row_table_high"] = assembler.address + 1
    for row_base in font_row_cpus:
        assembler.emit(row_base & 0xFF, row_base >> 8)
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

    row_cpus = _resolve_font_row_cpus(layout, len(glyphs.characters))
    code, labels = _emit_runtime(
        layout,
        glyph_count=len(glyphs.characters),
        space_glyph_id=space_id,
        question_glyph_id=question_id,
        font_row_cpus=row_cpus,
    )
    font_rows = _font_rows(atlas)

    # Code must not overlap any assigned font row in CPU address space.
    code_start = layout.code_cpu
    code_end = code_start + len(code)
    for row_cpu in row_cpus:
        row_end = row_cpu + len(glyphs.characters)
        if code_start < row_end and code_end > row_cpu:
            raise NativeEnglishRuntimeError(
                f"{layout.label}: runtime code overlaps font row at 0x{row_cpu:04X}"
            )

    return NativeOverlayRuntime(
        layout=layout,
        code=code,
        font_row_bytes=font_rows,
        font_row_cpus=row_cpus,
        labels=labels,
        glyph_count=len(glyphs.characters),
        space_glyph_id=space_id,
        question_glyph_id=question_id,
    )


def overlay_runtime_patches(runtime: NativeOverlayRuntime) -> tuple[PayloadPatch, ...]:
    layout = runtime.layout
    patches: list[PayloadPatch] = [
        PayloadPatch(
            offset=layout.parser_hook_offset,
            expected=bytes.fromhex("C9 80 F0"),
            replacement=bytes((0x4C, layout.code_cpu & 0xFF, layout.code_cpu >> 8)),
            label=f"{layout.label}: native-English parser trampoline",
        ),
        PayloadPatch(
            offset=layout.font_hook_offset,
            expected=FONT_FETCH_HOOK_EXPECTED,
            replacement=bytes(
                (0x20, runtime.glyph_hook_cpu & 0xFF, runtime.glyph_hook_cpu >> 8)
            ),
            label=f"{layout.label}: native-English fixed/VWF glyph compositor",
        ),
        PayloadPatch(
            offset=layout.payload_base + layout.code_cpu,
            expected=bytes((layout.code_fill,)) * len(runtime.code),
            replacement=runtime.code,
            label=f"{layout.label}: native-English runtime code",
        ),
    ]

    for region in layout.font_regions:
        region_bytes = b"".join(
            runtime.font_row_bytes[row]
            for row in range(region.first_row, region.first_row + region.row_count)
        )
        patches.append(
            PayloadPatch(
                offset=layout.payload_base + region.cpu_address,
                expected=bytes((region.fill_byte,)) * len(region_bytes),
                replacement=region_bytes,
                label=(
                    f"{layout.label}: native-English font rows "
                    f"{region.first_row}-{region.first_row + region.row_count - 1}"
                ),
            )
        )
    return tuple(patches)


def build_native_runtime_patches(
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
    *,
    layouts: tuple[NativeOverlayLayout, ...] = TEXT_NATIVE_LAYOUTS,
) -> tuple[PayloadPatch, ...]:
    patches: list[PayloadPatch] = []
    for layout in layouts:
        patches.extend(
            overlay_runtime_patches(build_overlay_runtime(layout, glyphs, atlas))
        )
    return tuple(patches)


def build_mission0_native_runtime_patches(
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
) -> tuple[PayloadPatch, ...]:
    return build_native_runtime_patches(
        glyphs,
        atlas,
        layouts=MISSION0_NATIVE_LAYOUTS,
    )
