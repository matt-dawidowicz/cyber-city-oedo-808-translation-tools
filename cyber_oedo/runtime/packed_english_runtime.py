"""Source-guarded Mission 0 packed-English renderer proof.

This is the first activation step for the collision-free English font design.
It deliberately does *not* replace or hook the dialogue parser.  The stock
parser already treats the reserved F0-FC lead range as ordinary two-byte
glyphs.  Only the stock EX_GETFNT call is intercepted.

For a private token the hook:

1. converts lead/trail bytes to a dictionary index;
2. looks up two one-byte English glyph IDs;
3. reads the corresponding 8x16 rows from a row-major atlas; and
4. writes the resulting 16 rows x 2 bytes directly to the existing $4C6C
   System Card glyph staging buffer.

Everything after the font fetch remains stock: the local transform, VDC
transfer, BAT write, cursor, grid, scroll, timing, and page/window behavior.

The initial proof uses the authenticated Mission 0-B resident overlay's
$A300-$BFFF padding region.  That region is source-guarded by an exact SHA-256
and exact byte pattern.  This is a bounded Mission 0 runtime proof, not yet a
claim that the same storage is safe in every mission overlay.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.text.font_atlas import GLYPH_HEIGHT, RasterizedAtlas
from cyber_oedo.text.packed_english import (
    PRIVATE_LEADS,
    PRIVATE_TRAILS,
    GlyphRepertoire,
    PackedEnglishDictionary,
)

MISSION0_B_PAYLOAD_BASE = 0x00131800

FONT_FETCH_HOOK_CPU = 0x56C0
FONT_FETCH_HOOK_OFFSET = MISSION0_B_PAYLOAD_BASE + FONT_FETCH_HOOK_CPU
FONT_FETCH_HOOK_EXPECTED = bytes.fromhex("20 60 E0")
SYSTEM_CARD_EX_GETFNT = 0xE060
FONT_STAGE_BUFFER = 0x4C6C

RUNTIME_CODE_CPU = 0xA300
PAIR_TABLE_CPU = 0xA500
RUNTIME_REGION_END_CPU = 0xC000
PADDING_SPLIT_CPU = 0xA800
RUNTIME_REGION_SHA256 = (
    "c4b3d9d150441e0fb914e0d8f8ffaf0e73c6b7e7037759fff4eb8a7c762fe18b"
)

# The redraw path copies the first stored glyph byte to $03 and the second to
# $02, then FONT_FETCH stores them as $F9 and $F8 respectively before the BIOS
# call.  Therefore $F9 is the private lead and $F8 is the private trail here.
GLYPH_TRAIL_ZP = 0xF8
GLYPH_LEAD_ZP = 0xF9

# Scratch zero-page bytes are safe inside the stock $5693 font routine: the
# caller has already stacked the outer $00-$05 values, and after the font fetch
# it immediately establishes fresh scratch state before those values are
# restored at routine exit.
POINTER_LO_ZP = 0x00
POINTER_HI_ZP = 0x01
INDEX_LO_ZP = 0x04
INDEX_HI_ZP = 0x05

IGNORED_FIELD_PADDING = 0x80

BARTENDER_PROOF_OFFSET = 0x00145892
BARTENDER_PROOF_SOURCE = bytes.fromhex(
    "83 6F 81 5B 83 65 83 93 81 75 82 A2 82 E7 82 C1 "
    "82 B5 82 E1 82 A2 82 DC 82 B9 81 76"
)
BARTENDER_PROOF_ENGLISH = "Bartender: ‘Welcome.’"


class PackedRuntimeError(ValueError):
    """Raised when a runtime layout or proof patch violates a hard gate."""


class _Assembler:
    """Tiny HuC6280 assembler for the renderer hook's instruction subset."""

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
            raise PackedRuntimeError("assembly byte lies outside 0x00..0xFF")
        self.code.extend(values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise PackedRuntimeError(f"duplicate assembly label: {name}")
        self.labels[name] = self.address

    def immediate(self, opcode: int, value: int) -> None:
        self.emit(opcode, value)

    def zero_page(self, opcode: int, address: int) -> None:
        self.emit(opcode, address)

    def absolute(self, opcode: int, address: int) -> None:
        if not 0 <= address <= 0xFFFF:
            raise PackedRuntimeError("absolute address lies outside 16-bit space")
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
                raise PackedRuntimeError(f"unknown assembly label: {target}")
            address = self.labels[target]
            if kind == "absolute":
                self.code[position] = address & 0xFF
                self.code[position + 1] = address >> 8
                continue
            displacement = address - (self.origin + position + 1)
            if not -128 <= displacement <= 127:
                raise PackedRuntimeError(f"branch to {target} is out of range")
            self.code[position] = displacement & 0xFF
        return bytes(self.code)


@dataclass(frozen=True, slots=True)
class PackedRuntime:
    """Generated Mission 0-B code/data and resolved runtime addresses."""

    code: bytes
    pair_table: bytes
    atlas_row_major: bytes
    atlas_cpu: int
    labels: dict[str, int]
    pair_count: int
    glyph_count: int
    question_glyph_id: int

    @property
    def code_end_cpu(self) -> int:
        return RUNTIME_CODE_CPU + len(self.code)

    @property
    def pair_table_end_cpu(self) -> int:
        return PAIR_TABLE_CPU + len(self.pair_table)

    @property
    def atlas_end_cpu(self) -> int:
        return self.atlas_cpu + len(self.atlas_row_major)

    @property
    def glyph_hook_cpu(self) -> int:
        return self.labels["glyph_hook"]

    def layout_report(self) -> dict[str, int | str]:
        return {
            "code_cpu": f"0x{RUNTIME_CODE_CPU:04X}",
            "code_bytes": len(self.code),
            "code_end_cpu": f"0x{self.code_end_cpu:04X}",
            "pair_table_cpu": f"0x{PAIR_TABLE_CPU:04X}",
            "pair_table_bytes": len(self.pair_table),
            "pair_table_end_cpu": f"0x{self.pair_table_end_cpu:04X}",
            "atlas_cpu": f"0x{self.atlas_cpu:04X}",
            "atlas_bytes": len(self.atlas_row_major),
            "atlas_end_cpu": f"0x{self.atlas_end_cpu:04X}",
            "pair_count": self.pair_count,
            "glyph_count": self.glyph_count,
        }


@dataclass(frozen=True, slots=True)
class Mission0PackedProof:
    """Complete source-guarded patch set for one Mission 0 visual proof."""

    runtime: PackedRuntime
    patches: tuple[PayloadPatch, ...]
    english: str

    def changed_payload_bytes(self) -> int:
        return sum(
            sum(before != after for before, after in zip(patch.expected, patch.replacement))
            for patch in self.patches
        )


def compact_repertoire_for_texts(texts: Iterable[str]) -> GlyphRepertoire:
    """Keep only display characters that the supplied English actually uses."""

    material = tuple(texts)
    used = set("".join(material))
    # Space is required for odd-length pair padding and '?' is the runtime
    # corruption/fallback glyph even when neither happens to appear in a
    # particular proof corpus.
    used.update((" ", "?"))
    from cyber_oedo.text.packed_english import DEFAULT_DISPLAY_CHARACTERS

    unknown = used.difference(DEFAULT_DISPLAY_CHARACTERS)
    if unknown:
        rendered = ", ".join(repr(character) for character in sorted(unknown))
        raise PackedRuntimeError(f"text uses unsupported display characters: {rendered}")
    characters = "".join(
        character
        for character in DEFAULT_DISPLAY_CHARACTERS
        if character in used
    )
    return GlyphRepertoire(characters)


def atlas_row_major_bytes(atlas: RasterizedAtlas) -> bytes:
    """Transpose glyph-major 8x16 bitmaps for fast row/index addressing."""

    return bytes(
        atlas.glyphs[glyph_id][row]
        for row in range(GLYPH_HEIGHT)
        for glyph_id in range(len(atlas.glyphs))
    )


def _align_up(value: int, alignment: int) -> int:
    if alignment <= 0 or alignment & (alignment - 1):
        raise PackedRuntimeError("alignment must be a positive power of two")
    return (value + alignment - 1) & ~(alignment - 1)


def _expected_padding(cpu_start: int, length: int) -> bytes:
    """Return the exact authenticated M0-B padding pattern for a subrange."""

    if length <= 0:
        raise PackedRuntimeError("runtime patch length must be positive")
    cpu_end = cpu_start + length
    if cpu_start < RUNTIME_CODE_CPU or cpu_end > RUNTIME_REGION_END_CPU:
        raise PackedRuntimeError("runtime data lies outside the guarded M0-B region")
    return bytes(
        0x00 if address < PADDING_SPLIT_CPU else 0xE5
        for address in range(cpu_start, cpu_end)
    )


def validate_runtime_region(payload: bytes) -> bool:
    """Authenticate the complete $A300-$BFFF Mission 0-B candidate region."""

    start = MISSION0_B_PAYLOAD_BASE + RUNTIME_CODE_CPU
    end = MISSION0_B_PAYLOAD_BASE + RUNTIME_REGION_END_CPU
    actual = payload[start:end]
    expected_length = RUNTIME_REGION_END_CPU - RUNTIME_CODE_CPU
    if len(actual) != expected_length:
        return False
    if hashlib.sha256(actual).hexdigest() != RUNTIME_REGION_SHA256:
        return False
    return actual == _expected_padding(RUNTIME_CODE_CPU, expected_length)


def _emit_runtime_code(
    pair_count: int,
    atlas_cpu: int,
    glyph_count: int,
    question_glyph_id: int,
) -> tuple[bytes, dict[str, int]]:
    """Assemble the private-token decoder and 8x16 staging compositor."""

    if not 0 < pair_count <= len(PRIVATE_LEADS) * len(PRIVATE_TRAILS):
        raise PackedRuntimeError("pair count lies outside the private token namespace")
    if not 0 < glyph_count <= 0xFF:
        raise PackedRuntimeError("glyph count must fit one byte")
    if not 0 <= question_glyph_id < glyph_count:
        raise PackedRuntimeError("question glyph ID lies outside the atlas")

    assembler = _Assembler(RUNTIME_CODE_CPU)
    assembler.label("glyph_hook")

    # Initial private-lead test. Stock Shift-JIS falls straight through to the
    # exact BIOS service that the overwritten JSR originally called.
    assembler.zero_page(0xA5, GLYPH_LEAD_ZP)  # LDA $F9
    assembler.immediate(0xC9, PRIVATE_LEADS[0])  # CMP #$F0
    assembler.branch(0x90, "stock_glyph")  # BCC
    assembler.immediate(0xC9, PRIVATE_LEADS[-1] + 1)  # CMP #$FD
    assembler.branch(0xB0, "stock_glyph")  # BCS
    assembler.absolute_label(0x4C, "custom_glyph")  # JMP

    assembler.label("stock_glyph")
    assembler.absolute(0x20, SYSTEM_CARD_EX_GETFNT)  # JSR $E060
    assembler.emit(0x60)  # RTS

    assembler.label("custom_glyph")
    # Preserve caller index registers. The stock BIOS call owns its own
    # register contract; our custom path should not introduce additional
    # X/Y clobbering beyond the replaced service.
    assembler.emit(0xDA)  # PHX
    assembler.emit(0x5A)  # PHY

    # X = private lead index, then multiply that index by 188 into $04/$05.
    assembler.zero_page(0xA5, GLYPH_LEAD_ZP)
    assembler.emit(0x38)  # SEC
    assembler.immediate(0xE9, PRIVATE_LEADS[0])  # SBC #$F0
    assembler.emit(0xAA)  # TAX
    assembler.zero_page(0x64, INDEX_LO_ZP)  # STZ $04
    assembler.zero_page(0x64, INDEX_HI_ZP)  # STZ $05

    assembler.label("lead_multiply")
    assembler.immediate(0xE0, 0)  # CPX #0
    assembler.branch(0xF0, "decode_trail")
    assembler.emit(0x18)  # CLC
    assembler.zero_page(0xA5, INDEX_LO_ZP)
    assembler.immediate(0x69, len(PRIVATE_TRAILS))  # ADC #188
    assembler.zero_page(0x85, INDEX_LO_ZP)
    assembler.zero_page(0xA5, INDEX_HI_ZP)
    assembler.immediate(0x69, 0)
    assembler.zero_page(0x85, INDEX_HI_ZP)
    assembler.emit(0xCA)  # DEX
    assembler.branch(0x80, "lead_multiply")  # BRA

    assembler.label("decode_trail")
    assembler.zero_page(0xA5, GLYPH_TRAIL_ZP)
    assembler.immediate(0xC9, 0x40)
    assembler.branch(0x90, "stock_stub")
    assembler.immediate(0xC9, 0x7F)
    assembler.branch(0x90, "low_trail")
    assembler.immediate(0xC9, 0x80)
    assembler.branch(0x90, "stock_stub")
    assembler.immediate(0xC9, 0xFD)
    assembler.branch(0xB0, "stock_stub")
    assembler.emit(0x38)  # SEC
    assembler.immediate(0xE9, 0x41)  # $80->$3F ... $FC->$BB
    assembler.branch(0x80, "add_trail")

    assembler.label("stock_stub")
    assembler.absolute_label(0x4C, "stock_glyph")

    assembler.label("low_trail")
    assembler.emit(0x38)
    assembler.immediate(0xE9, 0x40)

    assembler.label("add_trail")
    assembler.emit(0x18)
    assembler.zero_page(0x65, INDEX_LO_ZP)  # ADC $04
    assembler.zero_page(0x85, INDEX_LO_ZP)
    assembler.branch(0x90, "validate_index")
    assembler.zero_page(0xE6, INDEX_HI_ZP)  # INC $05

    assembler.label("validate_index")
    pair_hi = pair_count >> 8
    pair_lo = pair_count & 0xFF
    assembler.zero_page(0xA5, INDEX_HI_ZP)
    assembler.immediate(0xC9, pair_hi)
    assembler.branch(0x90, "valid_index")
    assembler.branch(0xD0, "invalid_index")
    assembler.zero_page(0xA5, INDEX_LO_ZP)
    assembler.immediate(0xC9, pair_lo)
    assembler.branch(0x90, "valid_index")
    assembler.branch(0x80, "invalid_index")

    assembler.label("valid_index")
    # Two glyph IDs per pair-table entry.
    assembler.zero_page(0x06, INDEX_LO_ZP)  # ASL $04
    assembler.zero_page(0x26, INDEX_HI_ZP)  # ROL $05
    assembler.emit(0x18)
    assembler.zero_page(0xA5, INDEX_LO_ZP)
    assembler.immediate(0x69, PAIR_TABLE_CPU & 0xFF)
    assembler.zero_page(0x85, POINTER_LO_ZP)
    assembler.zero_page(0xA5, INDEX_HI_ZP)
    assembler.immediate(0x69, PAIR_TABLE_CPU >> 8)
    assembler.zero_page(0x85, POINTER_HI_ZP)
    assembler.immediate(0xA0, 0)  # LDY #0
    assembler.emit(0xB1, POINTER_LO_ZP)  # LDA ($00),Y
    assembler.emit(0xAA)  # TAX = left glyph ID
    assembler.emit(0xC8)  # INY
    assembler.emit(0xB1, POINTER_LO_ZP)
    assembler.emit(0xA8)  # TAY = right glyph ID
    assembler.branch(0x80, "compose")

    assembler.label("invalid_index")
    assembler.immediate(0xA2, question_glyph_id)  # LDX #?
    assembler.immediate(0xA0, question_glyph_id)  # LDY #?

    assembler.label("compose")
    # Row-major atlas lets X/Y stay as glyph IDs for all sixteen scanlines.
    for row in range(GLYPH_HEIGHT):
        row_base = atlas_cpu + row * glyph_count
        destination = FONT_STAGE_BUFFER + row * 2
        assembler.absolute(0xBD, row_base)  # LDA row_base,X
        assembler.absolute(0x8D, destination)  # STA left staging byte
        assembler.absolute(0xB9, row_base)  # LDA row_base,Y
        assembler.absolute(0x8D, destination + 1)  # STA right staging byte
    assembler.emit(0x7A)  # PLY
    assembler.emit(0xFA)  # PLX
    assembler.emit(0x60)  # RTS

    return assembler.finish(), dict(assembler.labels)


def build_runtime(
    dictionary: PackedEnglishDictionary,
    atlas: RasterizedAtlas,
) -> PackedRuntime:
    """Build a bounded Mission 0-B packed-English renderer image."""

    if atlas.characters != dictionary.repertoire.characters:
        raise PackedRuntimeError(
            "atlas character order must exactly match dictionary repertoire"
        )
    pair_table = dictionary.runtime_pair_table()
    atlas_bytes = atlas_row_major_bytes(atlas)
    atlas_cpu = _align_up(PAIR_TABLE_CPU + len(pair_table), 0x100)
    try:
        question_glyph_id = dictionary.repertoire.glyph_id("?")
    except ValueError as error:
        raise PackedRuntimeError("English repertoire must contain '?'") from error

    code, labels = _emit_runtime_code(
        len(dictionary.pairs),
        atlas_cpu,
        len(atlas.characters),
        question_glyph_id,
    )
    runtime = PackedRuntime(
        code=code,
        pair_table=pair_table,
        atlas_row_major=atlas_bytes,
        atlas_cpu=atlas_cpu,
        labels=labels,
        pair_count=len(dictionary.pairs),
        glyph_count=len(atlas.characters),
        question_glyph_id=question_glyph_id,
    )
    if runtime.code_end_cpu > PAIR_TABLE_CPU:
        raise PackedRuntimeError("runtime code overlaps the pair table")
    if runtime.pair_table_end_cpu > runtime.atlas_cpu:
        raise PackedRuntimeError("pair table overlaps the aligned atlas")
    if runtime.atlas_end_cpu > RUNTIME_REGION_END_CPU:
        raise PackedRuntimeError(
            "runtime code/table/atlas exceed the guarded Mission 0-B region"
        )
    return runtime


def runtime_payload_patches(runtime: PackedRuntime) -> tuple[PayloadPatch, ...]:
    """Return the source-guarded hook/code/table/atlas payload patches."""

    return (
        PayloadPatch(
            offset=FONT_FETCH_HOOK_OFFSET,
            expected=FONT_FETCH_HOOK_EXPECTED,
            replacement=bytes(
                (
                    0x20,
                    runtime.glyph_hook_cpu & 0xFF,
                    runtime.glyph_hook_cpu >> 8,
                )
            ),
            label=(
                "Mission 0-B font fetch: JSR packed-English compositor "
                "with stock EX_GETFNT fallback"
            ),
        ),
        PayloadPatch(
            offset=MISSION0_B_PAYLOAD_BASE + RUNTIME_CODE_CPU,
            expected=_expected_padding(RUNTIME_CODE_CPU, len(runtime.code)),
            replacement=runtime.code,
            label="Mission 0-B packed-English private-token decoder/compositor",
        ),
        PayloadPatch(
            offset=MISSION0_B_PAYLOAD_BASE + PAIR_TABLE_CPU,
            expected=_expected_padding(PAIR_TABLE_CPU, len(runtime.pair_table)),
            replacement=runtime.pair_table,
            label="Mission 0-B packed-English pair dictionary",
        ),
        PayloadPatch(
            offset=MISSION0_B_PAYLOAD_BASE + runtime.atlas_cpu,
            expected=_expected_padding(runtime.atlas_cpu, len(runtime.atlas_row_major)),
            replacement=runtime.atlas_row_major,
            label="Mission 0-B row-major 8x16 English glyph atlas",
        ),
    )


def encode_fixed_footprint(
    dictionary: PackedEnglishDictionary,
    english: str,
    footprint: int,
) -> bytes:
    """Pack visible English and fill the unused source field with stock 0x80."""

    if footprint <= 0:
        raise PackedRuntimeError("text footprint must be positive")
    encoded = dictionary.encode_visible_text(english)
    if len(encoded) > footprint:
        raise PackedRuntimeError(
            f"packed English requires {len(encoded)} bytes; footprint is {footprint}"
        )
    return encoded + bytes((IGNORED_FIELD_PADDING,)) * (footprint - len(encoded))


def build_bartender_proof(
    dictionary: PackedEnglishDictionary,
    atlas: RasterizedAtlas,
    *,
    english: str = BARTENDER_PROOF_ENGLISH,
) -> Mission0PackedProof:
    """Build the runtime plus one easy-to-replay Mission 0 bartender proof."""

    runtime = build_runtime(dictionary, atlas)
    text_patch = PayloadPatch(
        offset=BARTENDER_PROOF_OFFSET,
        expected=BARTENDER_PROOF_SOURCE,
        replacement=encode_fixed_footprint(
            dictionary,
            english,
            len(BARTENDER_PROOF_SOURCE),
        ),
        label="Mission 0 bartender packed-English visual proof",
    )
    return Mission0PackedProof(
        runtime=runtime,
        patches=runtime_payload_patches(runtime) + (text_patch,),
        english=english,
    )


def validate_proof_against_payload(
    payload: bytes,
    proof: Mission0PackedProof,
) -> tuple[dict[str, int | str | bool], ...]:
    """Validate every proof patch against an authenticated Track 2 payload."""

    rows = []
    for patch in proof.patches:
        actual = payload[patch.offset : patch.end_offset]
        rows.append(
            {
                "label": patch.label,
                "offset": f"0x{patch.offset:08X}",
                "bytes": len(patch.expected),
                "matched": actual == patch.expected,
            }
        )
    return tuple(rows)
