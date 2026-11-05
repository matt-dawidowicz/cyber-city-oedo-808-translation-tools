"""Opt-in Mission 0-B banked English proof; NEVER a release build.

The game's indexed-record loader copies LBA $107D source bytes to RAM $A400.
We extend that proven load from $0301 to $1C00 bytes, making an atlas resident
at $A800 and an English interpreter at $B000. A separate source mapping
(source base + CPU - $400) is essential: using base + CPU directly would patch
disc bytes that are NOT installed into the intended runtime addresses.

A single verified original Japanese bartender record is converted to a private
$7B redirect. The five-byte body preserves the ORIGINAL source terminator
address via a u16 skip count, so the outer script resumes at its original
boundary. Pool data lives in the authenticated zero tail of Track 2. No source
game files are distributed or edited in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import tempfile
from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.disc.game_layout import TRACK2_SECTOR_COUNT, TRACK2_START_LBA
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.external_english_pool import (
    POOL_CAPACITY,
    POOL_FIRST_BANK,
    inspect_native_pool_record,
)
from cyber_oedo.runtime.native_english_runtime import (
    FONT_FETCH_HOOK_EXPECTED,
    FONT_FETCH_HOOK_CPU,
    M0B_PARSER_ENTRY,
    M0B_STREAM_ADVANCE_CPU,
    M0B_STREAM_READ_CPU,
    NativeOverlayLayout,
    FontRegion,
    _Assembler,
    build_overlay_runtime,
)
from cyber_oedo.text.english_dialogue_engine import (
    EnglishGlyphTable,
    encode_english_segment,
    wrap_english,
)
from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas, rasterize_atlas

TRACK2_SHA256 = "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"
M0B_SOURCE_BASE = 0x00131800
M0B_TABLE_SOURCE_LBA = 0x107D
M0B_TABLE_READ_BYTES = 0x1C00
M0B_TABLE_LOADER_CPU = 0x64DF
M0B_TABLE_LOADER_EXPECTED = bytes.fromhex("A9 01 85 06 A9 03 85 07")
M0B_TABLE_LOADER_REPLACEMENT = bytes.fromhex("A9 00 85 06 A9 1C 85 07")
POOL_START_RELATIVE_SECTOR = 0xA059
POOL_START_ABSOLUTE_LBA = TRACK2_START_LBA + POOL_START_RELATIVE_SECTOR
POOL_SECTORS = POOL_CAPACITY // 2048
# Extra authenticated all-zero tail sectors hold pre-rendered proportional
# bitmap cells. Never collide with the $7C-$7F four-bank stream pool.
VWF_SECTOR_RELATIVE = POOL_START_RELATIVE_SECTOR + POOL_SECTORS
VWF_SECTOR_ABSOLUTE = POOL_START_ABSOLUTE_LBA + POOL_SECTORS
VWF_BANK = 0x73
VWF_BANK_BYTES = 0x2000
# Exact source marker is at $00145890; Japanese text follows at $00145892.
BARTENDER_MARKER_OFFSET = 0x00145890
BARTENDER_SOURCE_TEXT = "バーテン「いらっしゃいませ」"
DEFAULT_PILOT_TEXT = "Bartender: Welcome."
SOURCE_REDIRECT_BYTES = 5  # 7B pool_u16le source_skip_u16le; NO early 00.
DIAGNOSTIC_INTRO_MARKER_OFFSET = 0x00175828
DIAGNOSTIC_INTRO_TERMINATOR_OFFSET = 0x00175ADF
DIAGNOSTIC_INTRO_RECORD_SHA256 = (
    "93afb245ad8ee5bf0ac1f1e8c712e6c35a4dd3b910725f88df3bb58145dbdc71"
)


# LBA $107D loads source [base+$A000, base+$BC00) into RAM $A400-$BFFF.
M0B_POOL_LAYOUT = NativeOverlayLayout(
    "MISSION_0_B_POOL", M0B_SOURCE_BASE, M0B_PARSER_ENTRY,
    0xB000, 0xE5, (FontRegion(0xA800, 0, 16, 0x00),),
)


@dataclass(frozen=True, slots=True)
class PilotRuntime:
    native_code: bytes
    full_code: bytes
    labels: dict[str, int]
    font: bytes


def _make_runtime(
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
    *,
    vwf_loader: bool = False,
) -> PilotRuntime:
    """Emit fixed/VWF English code followed by an experimental pool dispatcher."""
    native = build_overlay_runtime(
        M0B_POOL_LAYOUT, glyphs, atlas, pool_safe_read=True
    )
    asm = _Assembler(M0B_POOL_LAYOUT.code_cpu + len(native.code))

    def lda(name: str) -> None:
        asm.absolute_label(0xAD, name)

    def sta(name: str) -> None:
        asm.absolute_label(0x8D, name)

    def jsr(name: str) -> None:
        asm.absolute_label(0x20, name)

    def jmp(name: str) -> None:
        asm.absolute_label(0x4C, name)

    def immediate(value: int) -> None:
        asm.immediate(0xA9, value)

    asm.label("pool_dispatch")
    asm.immediate(0xC9, 0x7B)
    asm.branch(0xF0, "redirect")
    asm.absolute(0x4C, native.labels["parser_dispatch"])

    asm.label("redirect")
    jsr("pool_redirect")
    jmp("pool_parser_entry")

    asm.label("pool_parser_entry")
    lda("active")
    asm.branch(0xF0, "regular_parser_entry")
    # Check *top-level* termination before consuming it. A 00 operand in
    # $2A/$3D/$7E is not a terminator and must not restore the source stream.
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    asm.immediate(0xC9, 0x00)
    asm.branch(0xD0, "regular_parser_entry")
    jsr("restore_source")
    asm.label("regular_parser_entry")
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    asm.absolute(0x20, M0B_STREAM_ADVANCE_CPU)
    asm.absolute(0x4C, M0B_PARSER_ENTRY + 6)

    asm.label("restore_source")
    asm.absolute_label(0x9C, "active")  # STZ absolute
    lda("source_lo")
    asm.zero_page(0x85, 0x7F)
    lda("source_hi")
    asm.zero_page(0x85, 0x80)
    asm.emit(0x60)

    asm.label("pool_redirect")
    # Original parser has already consumed $7B. Preserve the source script
    # return position, not merely the end of the new five-byte redirect.
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    sta("offset_lo")
    asm.absolute(0x20, M0B_STREAM_ADVANCE_CPU)
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    sta("offset_hi")
    asm.absolute(0x20, M0B_STREAM_ADVANCE_CPU)
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    sta("skip_lo")
    asm.absolute(0x20, M0B_STREAM_ADVANCE_CPU)
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    sta("skip_hi")
    asm.absolute(0x20, M0B_STREAM_ADVANCE_CPU)

    asm.zero_page(0xA5, 0x7F)
    asm.emit(0x18)
    asm.absolute_label(0x6D, "skip_lo")  # ADC absolute
    sta("source_lo")
    asm.zero_page(0xA5, 0x80)
    asm.absolute_label(0x6D, "skip_hi")
    sta("source_hi")
    lda("source_lo")
    asm.zero_page(0x85, 0x7F)
    lda("source_hi")
    asm.zero_page(0x85, 0x80)
    # Verify the original terminator at the computed source location.
    asm.absolute(0x20, M0B_STREAM_READ_CPU)
    asm.immediate(0xC9, 0x00)
    asm.branch(0xD0, "reject_redirect")
    lda("offset_hi")
    asm.immediate(0xC9, 0x80)
    asm.branch(0xB0, "reject_redirect")

    jsr("pool_load")
    lda("load_error")
    asm.branch(0xD0, "reject_redirect")

    lda("offset_lo")
    asm.zero_page(0x85, 0x7F)
    lda("offset_hi")
    asm.emit(0x29, 0x1F)  # AND #$1F
    asm.emit(0x09, 0x60)  # ORA #$60
    asm.zero_page(0x85, 0x80)
    lda("offset_hi")
    for _ in range(5):
        asm.emit(0x4A)
    asm.emit(0x18)
    asm.immediate(0x69, POOL_FIRST_BANK)
    sta("pool_bank")
    immediate(1)
    sta("active")
    asm.emit(0x60)

    asm.label("reject_redirect")
    jsr("restore_source")
    asm.emit(0x60)

    # Keep the stock MPR3 mapping installed outside the actual read. Stock
    # indirect-text and other code executes in that mapped $6000-$7FFF bank.
    asm.label("pool_read")
    lda("active")
    asm.branch(0xF0, "plain_read")
    asm.emit(0x08)  # PHP
    asm.emit(0x78)  # SEI
    asm.emit(0x43, 0x08)  # TMA #$08
    asm.emit(0x48)  # PHA original MPR3
    lda("pool_bank")
    asm.emit(0x53, 0x08)  # TAM #$08
    asm.emit(0xB2, 0x7F)  # LDA ($7F), transiently mapped
    sta("read_value")
    asm.emit(0x68)  # PLA original MPR3
    asm.emit(0x53, 0x08)
    asm.emit(0x28)  # PLP
    lda("read_value")
    asm.emit(0x60)
    asm.label("plain_read")
    asm.emit(0xB2, 0x7F, 0x60)

    asm.label("pool_advance")
    asm.emit(0x48)  # PHA: stock $9F14 preserves A
    asm.zero_page(0xE6, 0x7F)
    asm.branch(0xD0, "advanced")
    asm.zero_page(0xE6, 0x80)
    asm.label("advanced")
    lda("active")
    asm.branch(0xF0, "advance_done")
    asm.zero_page(0xA5, 0x80)
    asm.immediate(0xC9, 0x80)
    asm.branch(0xD0, "advance_done")
    asm.immediate(0xA9, 0x60)
    asm.zero_page(0x85, 0x80)
    lda("pool_bank")
    asm.immediate(0xC9, 0x7F)
    asm.branch(0xD0, "next_pool_bank")
    jsr("restore_source")  # Reject wrap beyond $7F.
    asm.branch(0x80, "advance_done")
    asm.label("next_pool_bank")
    asm.absolute_label(0xEE, "pool_bank")  # INC absolute
    asm.label("advance_done")
    asm.emit(0x68, 0x60)  # PLA; RTS

    asm.label("pool_load")
    asm.emit(0xDA, 0x5A)  # PHX, PHY
    asm.emit(0x43, 0x08)  # Save MPR3 across all four CD_READ transfers.
    sta("old_mpr3")
    asm.immediate(0xA2, 0x00)  # LDX #0
    asm.label("save_cd_args")
    asm.emit(0xB5, 0xF8)  # LDA $F8,X
    asm.absolute_label(0x9D, "saved_cd_args")  # STA abs,X
    asm.emit(0xE8, 0xE0, 0x08)
    asm.branch(0xD0, "save_cd_args")
    asm.absolute_label(0x9C, "load_error")
    asm.absolute_label(0x9C, "chunk")

    asm.label("pool_load_loop")
    lda("chunk")
    asm.emit(0x18)
    asm.immediate(0x69, POOL_FIRST_BANK)
    asm.emit(0x53, 0x08)  # Selected 8-KiB Card RAM as MPR3.
    immediate(0)
    for zp in (0xFC, 0xF9, 0xFA):
        asm.zero_page(0x85, zp)
    immediate((POOL_START_ABSOLUTE_LBA >> 8) & 0xFF)
    asm.zero_page(0x85, 0xFD)
    lda("chunk")
    asm.emit(0x0A, 0x0A, 0x18)  # chunk * 4, CLC
    asm.immediate(0x69, POOL_START_ABSOLUTE_LBA & 0xFF)
    asm.zero_page(0x85, 0xFE)
    immediate(4)
    asm.zero_page(0x85, 0xF8)
    immediate(0x60)
    asm.zero_page(0x85, 0xFB)
    immediate(1)
    asm.zero_page(0x85, 0xFF)
    asm.absolute(0x20, 0xE009)  # BIOS CD_READ
    sta("load_error")
    asm.branch(0xD0, "pool_load_cleanup")
    asm.absolute_label(0xEE, "chunk")
    lda("chunk")
    asm.immediate(0xC9, 4)
    asm.branch(0xD0, "pool_load_loop")

    if vwf_loader:
        # Load the extra four VWF sectors into Super Card RAM bank $73 only
        # after all original pool reads complete. Existing pool_load cleanup
        # still restores MPR3 and all eight BIOS argument bytes on failure.
        immediate(VWF_BANK)
        asm.emit(0x53, 0x08)  # TAM #$08
        immediate(0)
        for zp in (0xFC, 0xF9, 0xFA):
            asm.zero_page(0x85, zp)
        immediate((VWF_SECTOR_ABSOLUTE >> 8) & 0xFF)
        asm.zero_page(0x85, 0xFD)
        immediate(VWF_SECTOR_ABSOLUTE & 0xFF)
        asm.zero_page(0x85, 0xFE)
        immediate(4)
        asm.zero_page(0x85, 0xF8)
        immediate(0x60)
        asm.zero_page(0x85, 0xFB)
        immediate(1)
        asm.zero_page(0x85, 0xFF)
        asm.absolute(0x20, 0xE009)  # BIOS CD_READ
        sta("load_error")

    asm.label("pool_load_cleanup")
    lda("old_mpr3")
    asm.emit(0x53, 0x08)
    asm.immediate(0xA2, 0x00)
    asm.label("restore_cd_args")
    asm.absolute_label(0xBD, "saved_cd_args")  # LDA abs,X
    asm.emit(0x95, 0xF8)  # STA $F8,X
    asm.emit(0xE8, 0xE0, 0x08)
    asm.branch(0xD0, "restore_cd_args")
    asm.emit(0x7A, 0xFA, 0x60)  # PLY, PLX, RTS

    for name, length in (
        ("active", 1),
        ("pool_bank", 1),
        ("source_lo", 1), ("source_hi", 1),
        ("offset_lo", 1), ("offset_hi", 1),
        ("skip_lo", 1), ("skip_hi", 1),
        ("read_value", 1),
        ("old_mpr3", 1),
        ("load_error", 1),
        ("chunk", 1),
        ("saved_cd_args", 8),
    ):
        asm.label(name)
        asm.emit(*([0] * length))

    extra = asm.finish()
    code = native.code + extra
    if M0B_POOL_LAYOUT.code_cpu + len(code) > 0xC000:
        raise ValueError("Mission 0-B code exceeds owned B000-BFFF source region")
    font = b"".join(native.font_row_bytes)
    if len(font) > 0x2000:
        raise ValueError("font exceeds the indexed-table loader's assigned region")
    return PilotRuntime(
        native_code=native.code,
        full_code=code,
        labels={**native.labels, **asm.labels},
        font=font,
    )


def _verify_original(payload: bytes) -> None:
    if hashlib.sha256(payload).hexdigest() != TRACK2_SHA256:
        raise ValueError("source payload is not the authenticated original game")
    text = BARTENDER_SOURCE_TEXT.encode("shift_jis")
    off = BARTENDER_MARKER_OFFSET
    if payload[off:off + 2] != bytes.fromhex("27 28"):
        raise ValueError("bartender dialogue marker is not the expected source")
    if payload[off + 2:off + 2 + len(text) + 1] != text + b"\x00":
        raise ValueError("bartender source text or original terminator changed")
    tail = payload[
        POOL_START_RELATIVE_SECTOR * 2048:
        (POOL_START_RELATIVE_SECTOR + POOL_SECTORS) * 2048
    ]
    if tail != bytes(POOL_CAPACITY):
        raise ValueError("English pool allocation is not authenticated empty tail")


def build_m0b_intro_diagnostic_patch(payload: bytes) -> PayloadPatch:
    """Source-guarded opening-narration redirect for NON-RELEASE tests only."""
    start = DIAGNOSTIC_INTRO_MARKER_OFFSET
    stop = DIAGNOSTIC_INTRO_TERMINATOR_OFFSET
    record = payload[start:stop + 1]
    if (
        len(record) != stop + 1 - start
        or not record.startswith(bytes.fromhex("27 28 81 75 89 B4 82"))
        or record[-1] != 0
        or 0 in record[2:-1]
        or hashlib.sha256(record).hexdigest() != DIAGNOSTIC_INTRO_RECORD_SHA256
    ):
        raise ValueError("intro diagnostic record does not match authenticated bytes")
    body_at = start + 2
    remaining = stop - (body_at + SOURCE_REDIRECT_BYTES)
    redirect = bytes.fromhex("7B 00 00") + remaining.to_bytes(2, "little")
    return PayloadPatch(
        body_at, record[2:2 + SOURCE_REDIRECT_BYTES], redirect,
        "DIAGNOSTIC-ONLY intro narration uses shared $7B pool renderer",
    )


def build_m0b_pilot_patches(
    payload: bytes,
    glyphs: EnglishGlyphTable,
    atlas: RasterizedAtlas,
    *,
    english: str = DEFAULT_PILOT_TEXT,
    diagnostic_intro_redirect: bool = False,
    vwf_pilot: bool = False,
) -> tuple[PayloadPatch, ...]:
    """Produce guarded modifications only; callers must supply a COPY of IMG."""
    _verify_original(payload)
    vwf_cells = None
    if vwf_pilot:
        from cyber_oedo.text.vwf_exact_cells import compile_exact_vwf
        from cyber_oedo.text.vwf_text import derive_vwf_font

        if atlas.characters != glyphs.characters:
            raise ValueError("VWF and native glyph maps have different order")
        font = derive_vwf_font(atlas.characters, atlas.glyphs)
        vwf_cells = compile_exact_vwf(english, font)
        if len(vwf_cells.staged_cells) > VWF_BANK_BYTES:
            raise ValueError("pilot VWF cells exceed owned 8 KiB Card RAM bank")
        compiled = vwf_cells.stream
    else:
        if len(wrap_english(english)) != 1:
            raise ValueError("pilot must fit in one 22-column fixed English line")
        compiled = encode_english_segment(english, glyphs) + b"\x00"
    if len(compiled) > POOL_CAPACITY:
        raise ValueError("pilot English text does not fit Card RAM")
    pool = compiled + bytes(POOL_CAPACITY - len(compiled))
    audit = inspect_native_pool_record(pool, 0)
    expected_vwf_segments = len(vwf_cells.line_texts) if vwf_cells else 0
    if (
        audit.vwf_segments != expected_vwf_segments
        or audit.fixed_segments != int(not vwf_pilot)
    ):
        raise ValueError("pool English stream audit disagrees with compiler")
    runtime = _make_runtime(glyphs, atlas, vwf_loader=vwf_pilot)
    labels = runtime.labels
    b = M0B_SOURCE_BASE
    original = BARTENDER_SOURCE_TEXT.encode("shift_jis")
    skip = len(original) - SOURCE_REDIRECT_BYTES
    if not 0 <= skip <= 0xFFFF:
        raise ValueError("original record cannot hold owned redirect")
    redirect = bytes((0x7B, 0, 0)) + skip.to_bytes(2, "little")
    # The installed table image is at disc base+$A000 onward and is loaded
    # to RAM $A400 onward. Font CPU $A800 -> disc base+$A400.
    font_expected = bytes(min(len(runtime.font), 0x400))
    font_expected += bytes((0xE5,)) * max(0, len(runtime.font) - 0x400)
    patches = (
        PayloadPatch(
            b + M0B_TABLE_LOADER_CPU,
            M0B_TABLE_LOADER_EXPECTED, M0B_TABLE_LOADER_REPLACEMENT,
            "M0-B source-guarded indexed table full-length load",
        ),
        PayloadPatch(
            b + M0B_PARSER_ENTRY, bytes.fromhex("20 11 9F"),
            bytes((0x4C, labels["pool_parser_entry"] & 255,
                   labels["pool_parser_entry"] >> 8)),
            "M0-B parser entry through pool-aware control hook",
        ),
        PayloadPatch(
            b + 0x95D4, bytes.fromhex("C9 80 F0"),
            bytes((0x4C, labels["pool_dispatch"] & 255,
                   labels["pool_dispatch"] >> 8)),
            "M0-B native $7B/$7D parser dispatcher",
        ),
        PayloadPatch(
            b + M0B_STREAM_READ_CPU, bytes.fromhex("B2 7F 60"),
            bytes((0x4C, labels["pool_read"] & 255, labels["pool_read"] >> 8)),
            "M0-B source/pool stream byte read",
        ),
        PayloadPatch(
            b + M0B_STREAM_ADVANCE_CPU,
            bytes.fromhex("E6 7F D0 02 E6 80"),
            bytes((0x4C, labels["pool_advance"] & 255,
                   labels["pool_advance"] >> 8, 0xEA, 0xEA, 0xEA)),
            "M0-B source/pool stream pointer advance",
        ),
        PayloadPatch(
            b + FONT_FETCH_HOOK_CPU, FONT_FETCH_HOOK_EXPECTED,
            bytes((0x20, labels["glyph_hook"] & 255,
                   labels["glyph_hook"] >> 8)),
            "M0-B original Japanese/native English font hook",
        ),
        PayloadPatch(
            b + 0xA400, font_expected, runtime.font,
            "M0-B atlas installed at CPU A800 by indexed table loader",
        ),
        PayloadPatch(
            b + 0xAC00, bytes((0xE5,)) * len(runtime.full_code),
            runtime.full_code,
            "M0-B pool-aware English code installed at CPU B000",
        ),
        PayloadPatch(
            POOL_START_RELATIVE_SECTOR * 2048, bytes(POOL_CAPACITY), pool,
            "M0-B first 16 tail sectors for four Card RAM banks",
        ),
        PayloadPatch(
            BARTENDER_MARKER_OFFSET + 2,
            original[:SOURCE_REDIRECT_BYTES], redirect,
            "M0-B bartender dialogue relocated without moving original terminator",
        ),
    )
    if vwf_cells is not None:
        dictionary = vwf_cells.staged_cells.ljust(VWF_BANK_BYTES, b"\x00")
        patches += (PayloadPatch(
            VWF_SECTOR_RELATIVE * 2048,
            bytes(VWF_BANK_BYTES), dictionary,
            "M0-B VWF exact 16px cell dictionary in source-guarded disc tail",
        ),)
    if diagnostic_intro_redirect:
        patches += (build_m0b_intro_diagnostic_patch(payload),)
    spans = sorted(
        (patch.offset, patch.offset + len(patch.expected), patch.label)
        for patch in patches
    )
    for left, right in zip(spans, spans[1:]):
        if right[0] < left[1]:
            raise ValueError("overlapping pilot patches: " + left[2] + " / " + right[2])
    for patch in patches:
        if payload[patch.offset:patch.offset + len(patch.expected)] != patch.expected:
            raise ValueError("source signature mismatch: " + patch.label)
    return patches



def render_pilot_mesen_trace(labels: dict[str, int]) -> str:
    """Generate a read-only trace using the exact assembled pilot addresses."""
    for key in ("pool_dispatch", "pool_redirect", "pool_read", "pool_load",
                "pool_advance", "active", "pool_bank", "source_lo", "source_hi"):
        if key not in labels or not 0xB000 <= labels[key] < 0xC000:
            raise ValueError("missing/out-of-range pool-runtime label: " + key)
    lua = r"""-- Read-only Mission 0-B experimental external-pool trace.
-- The generated values are the assembler's actual logical CPU addresses.
-- Instruction-entry hooks do not prove an operation completed.
local CPU = emu.cpuType.pce
local MEM = emu.memType.pceMemory
local hits = {redirect=0, load=0, read=0, render=0, source_return=0}
local triggered = false
local function r8(address) return emu.read(address, MEM) end
local function dp8(address) return r8(0x2000 + address) end
local function mprs()
  local s = emu.getState()
  local t = {}
  for i=0,7 do
    t[#t+1] = string.format("MPR%d=$%02X", i,
      s["memoryManager.mpr[" .. i .. "]"] or 0)
  end
  return table.concat(t, " ")
end
local function info(tag)
  local lo, hi = dp8(0x7F), dp8(0x80)
  local active = r8(0x__ACTIVE__)
  print(string.format(
    "[%s] frame=%d ptr=$%04X active=%d bank=$%02X "
      .. "source_return=$%02X%02X %s",
    tag, emu.getState()["frameCount"] or 0, lo | (hi << 8),
    active, r8(0x__BANK__), r8(0x__SRC_HI__), r8(0x__SRC_LO__),
    mprs()
  ))
  return active
end
local function on_pc(address, callback)
  emu.addMemoryCallback(callback, emu.callbackType.exec,
    address, address, CPU, MEM)
end
on_pc(0x__DISPATCH__, function()
  local c = emu.getCpuState(CPU)
  if c.a == 0x7B then
    hits.redirect = hits.redirect + 1
    triggered = true
    info("REDIRECT_OPCODE_BEFORE_EXEC")
  end
end)
on_pc(0x__LOAD__, function()
  if triggered then
    hits.load = hits.load + 1
    info("LOAD_ENTRY_BEFORE_CD")
  end
end)
on_pc(0x__READ__, function()
  if triggered then
    hits.read = hits.read + 1
    if hits.read <= 40 then info("BANKED_STREAM_READ_ENTRY") end
  end
end)
on_pc(0x__ADVANCE__, function()
  if triggered and hits.read <= 40 then info("STREAM_ADVANCE_ENTRY") end
end)
on_pc(0xE009, function()
  if not triggered then return end
  local lba = (dp8(0xFC) << 16) | (dp8(0xFD) << 8) | dp8(0xFE)
  if lba >= 0x__FIRST_LBA__ and lba <= 0x__LAST_LBA__ then
    print(string.format(
      "[POOL_BIOS_READ_BEFORE_EXEC] lba=$%06X blocks=$%02X "
        .. "destination=$%02X%02X mode=$%02X %s",
      lba, dp8(0xF8), dp8(0xFB), dp8(0xFA), dp8(0xFF), mprs()
    ))
  end
end)
on_pc(0x5915, function()
  if triggered then
    hits.render = hits.render + 1
    if hits.render <= 40 then info("RENDER_CELL_ENTRY") end
  end
end)
on_pc(0x9543, function()
  if triggered then
    local active = info("PARSER_ENTRY")
    if active == 0 then
      hits.source_return = hits.source_return + 1
    end
  end
end)
emu.addEventCallback(function()
  print(string.format(
    "=== PILOT TRACE SUMMARY: redirects=%d loads=%d reads=%d renders=%d "
      .. "inactive_parser_entries=%d ===",
    hits.redirect, hits.load, hits.read, hits.render, hits.source_return
  ))
  print("EMULATOR_CERTIFIED=false (inspect sequence, CD errors, state, "
    .. "and natural continuation manually)")
end, emu.eventType.scriptEnded)
"""
    replacements = {
        "__DISPATCH__": f"{labels['pool_dispatch']:04X}",
        "__LOAD__": f"{labels['pool_load']:04X}",
        "__READ__": f"{labels['pool_read']:04X}",
        "__ADVANCE__": f"{labels['pool_advance']:04X}",
        "__ACTIVE__": f"{labels['active']:04X}",
        "__BANK__": f"{labels['pool_bank']:04X}",
        "__SRC_HI__": f"{labels['source_hi']:04X}",
        "__SRC_LO__": f"{labels['source_lo']:04X}",
        "__FIRST_LBA__": f"{POOL_START_ABSOLUTE_LBA:06X}",
        "__LAST_LBA__": f"{POOL_START_ABSOLUTE_LBA + 12:06X}",
    }
    for key, value in replacements.items():
        lua = lua.replace(key, value)
    return lua


def build_m0b_pilot_disc(
    ccd: pathlib.Path,
    output_directory: pathlib.Path,
    font: pathlib.Path | None,
    *,
    english: str = DEFAULT_PILOT_TEXT,
    point_size: int = 13,
    diagnostic_intro_redirect: bool = False,
    authored_pixel_font: bool = False,
    vwf_pilot: bool = False,
) -> pathlib.Path:
    """Create a separate EXPERIMENTAL CloneCD copy. Never edit original media."""
    from cyber_oedo.build.profiles import mission0_stock
    from cyber_oedo.build.source import copy_authenticated_source_set
    from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload

    if vwf_pilot and not authored_pixel_font:
        raise ValueError("VWF live pilot requires the source-authored pixel font")
    glyphs = EnglishGlyphTable.from_texts((english, " ?"))
    if authored_pixel_font:
        # Original, source-authored 8x16 glyphs with shared baseline.
        # Live pilot remains fixed-cell; VWF metrics are for staged integration.
        from cyber_oedo.text.oedo_pixel_font import authored_atlas, authored_vwf

        atlas = authored_atlas(glyphs.characters)
        metrics = authored_vwf(glyphs.characters)
        glyph_metrics = {
            ch: {
                "ink_width": metrics.metric(ch).width,
                "advance": metrics.metric(ch).advance,
            }
            for ch in glyphs.characters
        }
    else:
        if font is None:
            raise ValueError("font path required unless --authored-pixel-font is set")
        atlas = rasterize_atlas(
            font, glyphs.characters,
            config=RasterConfig(point_size=point_size),
        )
        glyph_metrics = None
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise ValueError("output destination already exists")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temp = pathlib.Path(tempfile.mkdtemp(
        dir=output_directory.parent, prefix="m0b-pool-pilot."
    ))
    try:
        source_paths, output_paths = copy_authenticated_source_set(
            ccd, temp, "Cyber City Oedo 808 [M0B External Pool Pilot]",
            mission0_stock.SOURCE_HASHES,
        )
        payload_path = temp / "track02_mode1_2048.bin"
        size, digest = extract_mode1_payload(
            source_paths[".img"], payload_path,
            start_lba=TRACK2_START_LBA,
            sector_count=TRACK2_SECTOR_COUNT,
        )
        if size != TRACK2_SECTOR_COUNT * 2048 or digest != TRACK2_SHA256:
            raise ValueError("extracted disc payload is not authenticated")
        patches = build_m0b_pilot_patches(
            payload_path.read_bytes(), glyphs, atlas, english=english,
            diagnostic_intro_redirect=diagnostic_intro_redirect,
            vwf_pilot=vwf_pilot,
        )
        runtime = _make_runtime(glyphs, atlas, vwf_loader=vwf_pilot)
        reports = apply_payload_patches(
            output_paths[".img"], patches,
            start_lba=TRACK2_START_LBA,
            sector_count=TRACK2_SECTOR_COUNT,
        )
        manifest = {
            "profile": "EXPERIMENTAL-not-release-certified",
            "source_payload_sha256": digest,
            "english": english,
            "changed_sectors": sorted({
                x.relative_sector for x in reports
                if x.before_sha256 != x.after_sha256
            }),
            "font_sha256": atlas.source_sha256,
            "font_style": "authored_pixel" if authored_pixel_font else "external_ttf",
            "proportional_metrics": glyph_metrics,
            "proportional_runtime_certified": False,
            "vwf_pilot_enabled": vwf_pilot,
            "vwf_card_ram_bank": ("$73" if vwf_pilot else None),
            "vwf_disc_relative_sector": (
                VWF_SECTOR_RELATIVE if vwf_pilot else None
            ),
            "patches": [x.label for x in patches],
            "runtime_labels": {
                key: f"0x{value:04X}"
                for key, value in sorted(runtime.labels.items())
            },
            "runtime_code_sha256": hashlib.sha256(
                runtime.full_code
            ).hexdigest(),
            "source_record_terminator_offset": (
                f"0x{BARTENDER_MARKER_OFFSET + 2 + len(BARTENDER_SOURCE_TEXT.encode('shift_jis')):08X}"
            ),
            "release_enabled": False,
            "emulator_certified": False,
            "diagnostic_intro_redirect": diagnostic_intro_redirect,
            "natural_bartender_certified": False,
            "diagnostic_warning": (
                "Opening narration is substituted ONLY to test the $7B loader, "
                "not as game translation or natural bartender certification."
                if diagnostic_intro_redirect else None
            ),
        }
        (temp / "m0b_pool_pilot_manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        (temp / "mesen_m0b_pool_pilot_trace.lua").write_text(
            render_pilot_mesen_trace(runtime.labels), encoding="utf-8"
        )
        payload_path.unlink()
        temp.replace(output_directory)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return output_directory / "Cyber City Oedo 808 [M0B External Pool Pilot].ccd"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-release Mission 0-B external English pool proof"
    )
    parser.add_argument("source_ccd", type=pathlib.Path)
    parser.add_argument("output_directory", type=pathlib.Path)
    parser.add_argument(
        "font", type=pathlib.Path, nargs="?",
        help="External TTF/OTF path; omit with --authored-pixel-font",
    )
    parser.add_argument("--english", default=DEFAULT_PILOT_TEXT)
    parser.add_argument("--point-size", type=int, default=13)
    parser.add_argument(
        "--authored-pixel-font", action="store_true",
        help="NON-RELEASE: source-authored 8x16 glyphs and VWF metric manifest",
    )
    parser.add_argument(
        "--vwf-pilot", action="store_true",
        help="NON-RELEASE: render exact VWF cells through Card RAM bank $73",
    )
    parser.add_argument(
        "--diagnostic-intro-redirect", action="store_true",
        help="NON-RELEASE: run $7B from the authenticated opening narration",
    )
    args = parser.parse_args(argv)
    result = build_m0b_pilot_disc(
        args.source_ccd, args.output_directory, args.font,
        english=args.english, point_size=args.point_size,
        diagnostic_intro_redirect=args.diagnostic_intro_redirect,
        authored_pixel_font=args.authored_pixel_font,
        vwf_pilot=args.vwf_pilot,
    )
    print("output_ccd=" + str(result))
    print("release_enabled=false")
    print("emulator_certified=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
