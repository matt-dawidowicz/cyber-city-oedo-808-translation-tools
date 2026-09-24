"""Source-guarded Mission 0 stock text-renderer evidence."""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_file
from cyber_oedo.runtime.dialogue_interpreter import (
    MISSION0_MODULE_PAYLOAD_BASE,
    TRACK2_PAYLOAD_SHA256,
)


FONT_FETCH_CPU = 0x56AB
FONT_TRANSFORM_CPU = 0x4E86
VRAM_SETUP_CPU = 0x570C
VRAM_STREAM_CPU = 0x5772
BAT_WRITE_CPU = 0x4A38
GLYPH_CELL_CPU = 0x5915
GLYPH_GRID_CPU = 0x59B7

FONT_STAGE_BUFFER = 0x4C6C
FONT_TRANSFORM_BUFFER = 0x4C8C
SYSTEM_CARD_EX_GETFNT = 0xE060
SYSTEM_CARD_EX_VSYNC = 0xE07B
JOY_CURRENT = 0x2228
TEXT_DELAY_COUNTER = 0x2827


@dataclass(frozen=True, slots=True)
class RendererRegion:
    """One exact Mission 0 renderer code window."""

    name: str
    cpu_address: int
    expected: bytes
    purpose: str

    @property
    def payload_offset(self) -> int:
        return MISSION0_MODULE_PAYLOAD_BASE + self.cpu_address


RENDERER_REGIONS = (
    RendererRegion(
        "font_fetch",
        FONT_FETCH_CPU,
        bytes.fromhex(
            "A5 02 85 F8 A5 03 85 F9 A9 6C 85 FA A9 4C 85 FB "
            "A9 00 85 FF 78 20 60 E0 58 A9 00 8D 6A 4C "
            "A9 00 8D 6B 4C 20 86 4E"
        ),
        (
            "Copy the two-byte glyph code into the System Card AX workspace, "
            "select destination $4C6C and 16x16 mode, call EX_GETFNT, clear "
            "the adjacent staging bytes, and enter the local transform."
        ),
    ),
    RendererRegion(
        "font_transform",
        FONT_TRANSFORM_CPU,
        bytes.fromhex(
            "A5 00 48 A5 01 48 A5 02 48 A5 03 48 A5 04 48 A5 05 48 "
            "A9 6C 85 00 A9 4C 85 01 A9 8C 85 04 A9 4C 85 05 A2 10 "
            "C2 B1 00 C8 85 02 B1 00 85 03 06 03 26 02 A5 03 91 04 "
            "88 A5 02 91 04 C8 C8"
        ),
        (
            "Transform sixteen two-byte rows from the $4C6C font staging "
            "area into the $4C8C staging area."
        ),
    ),
    RendererRegion(
        "vram_setup",
        VRAM_SETUP_CPU,
        bytes.fromhex(
            "A9 00 85 F7 8D 00 00 A5 00 8D 02 00 A5 01 8D 03 00 "
            "A9 02 85 F7 8D 00 00 A9 8D 85 00 A9 4C 85 01 "
            "A9 8C 85 02 A9 4C 85 03 20 72 57 "
            "A9 6B 85 00 A9 4C 85 01 A9 6A 85 02 A9 4C 85 03 "
            "20 72 57"
        ),
        (
            "Select VDC MAWR and VWR, then stream transformed and original "
            "font staging data through the local VRAM writer."
        ),
    ),
    RendererRegion(
        "vram_stream",
        VRAM_STREAM_CPU,
        bytes.fromhex(
            "C2 B1 00 8D 02 00 B1 02 C8 8D 03 00 C8 C0 20 D0 F0 60"
        ),
        (
            "Write sixteen pairs from two source pointers to VDC data ports "
            "$0002/$0003."
        ),
    ),
    RendererRegion(
        "bat_write",
        BAT_WRITE_CPU,
        bytes.fromhex(
            "A5 00 48 A5 01 48 64 01 A5 00 18 65 00 85 00 "
            "A5 01 65 01 85 01 A5 00 18 65 00 85 00 "
            "A5 01 65 01 85 01 A5 00 18 65 34 85 00 "
            "A5 01 65 35 85 01 A5 00 18 69 03 85 00 "
            "A5 01 69 00 85 01 A9 00 85 F7 8D 00 00 "
            "A5 00 8D 02 00 A5 01 8D 03 00 A9 02 85 F7 "
            "8D 00 00 A5 02 8D 02 00 A5 03 8D 03 00"
        ),
        (
            "Compute a tilemap/BAT address from the caller index and base "
            "$34/$35, set VDC MAWR, and write one 16-bit cell entry."
        ),
    ),
    RendererRegion(
        "glyph_cell_dispatch",
        GLYPH_CELL_CPU,
        bytes.fromhex(
            "A5 00 48 A5 01 48 20 46 59 85 31 A5 30 C5 31 F0 04 "
            "B0 02 80 03 20 CE 58 A5 2F 85 00 A5 30 85 01 "
            "20 B7 59 20 80 59 85 31 E6 30 68 85 01 68 85 00 60"
        ),
        (
            "Apply the 11/12-cell line limit, advance/page as needed, stage "
            "the glyph in the text grid, apply punctuation timing, then "
            "advance the cell column."
        ),
    ),
)


def validate_renderer_regions(payload: pathlib.Path) -> tuple[dict[str, Any], ...]:
    """Validate exact renderer windows against a Track 2 payload."""

    results: list[dict[str, Any]] = []
    with payload.open("rb") as source:
        for region in RENDERER_REGIONS:
            source.seek(region.payload_offset)
            actual = source.read(len(region.expected))
            results.append(
                {
                    "name": region.name,
                    "cpu_address": f"0x{region.cpu_address:04X}",
                    "payload_offset": f"0x{region.payload_offset:08X}",
                    "bytes": len(region.expected),
                    "matched": actual == region.expected,
                    "purpose": region.purpose,
                }
            )
    return tuple(results)


def build_renderer_report(payload: pathlib.Path) -> dict[str, Any]:
    """Build a deterministic static proof report for the Mission 0 renderer."""

    digest = sha256_file(payload)
    regions = validate_renderer_regions(payload)
    return {
        "tier": "B-renderer-static",
        "scope": "Mission 0 stock 16x16 glyph staging and VDC transfer path",
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "all_source_guards_match": all(item["matched"] for item in regions),
        "regions": regions,
        "pipeline": {
            "glyph_code_source": "$02/$03",
            "system_card_font_service": f"0x{SYSTEM_CARD_EX_GETFNT:04X}",
            "font_stage_buffer": f"0x{FONT_STAGE_BUFFER:04X}",
            "font_transform_buffer": f"0x{FONT_TRANSFORM_BUFFER:04X}",
            "vram_stream_cpu": f"0x{VRAM_STREAM_CPU:04X}",
            "bat_write_cpu": f"0x{BAT_WRITE_CPU:04X}",
            "glyph_cell_cpu": f"0x{GLYPH_CELL_CPU:04X}",
            "text_grid_cpu": f"0x{GLYPH_GRID_CPU:04X}",
            "text_delay_counter": f"0x{TEXT_DELAY_COUNTER:04X}",
            "joy_current": f"0x{JOY_CURRENT:04X}",
            "system_card_vsync": f"0x{SYSTEM_CARD_EX_VSYNC:04X}",
        },
        "limits": {
            "proof_level": "static source-guarded",
            "vram_destination_semantics": (
                "address computation is proven; exact game-facing tile ownership "
                "still requires live VDC/VRAM correlation"
            ),
            "later_missions": "not implied by Mission 0 source identity",
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the source-guarded Mission 0 stock text renderer."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_renderer_report(args.payload)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["payload_authenticated"] and report["all_source_guards_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
