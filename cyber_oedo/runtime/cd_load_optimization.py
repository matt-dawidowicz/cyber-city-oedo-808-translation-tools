"""Compression and disc-layout experiments for hot scene-load assets.

The first deployable codec candidate is a 16-bit PackBits stream.  It is simple
enough for a small HuC6280 decoder and naturally matches the PC Engine VDC's
word-oriented data port.  This module is an analysis/build primitive only; it
does not patch the game until loader destination ownership is proven.

The zlib size reported by :func:`analyze_hot_assets` is an upper-bound
comparison, not a proposal to embed zlib in the game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import zlib
from dataclasses import dataclass

from cyber_oedo.disc.game_layout import TRACK2_START_LBA
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256

SECTOR_BYTES = 2048
CD_SECTORS_PER_SECOND = 75

MOVEMENT_MODULE_PAYLOAD_BASE = 0x000A4800
LOCAL_SCENE_LOADER_CPU = 0x423B
VRAM_SCENE_LOADER_CPU = 0x4262
LOCAL_SCENE_LOADER_BYTES = bytes.fromhex(
    "B2 1E 85 FC A0 01 B1 1E 85 FE C8 B1 1E 85 FD C8 "
    "B1 1E 85 F8 A5 1C 85 FA A5 1D 85 FB A9 01 85 FF "
    "20 09 E0 AA D0 DA 60"
)
VRAM_SCENE_LOADER_BYTES = bytes.fromhex(
    "B2 1E 85 FC A0 01 B1 1E 85 FE C8 B1 1E 85 FD C8 "
    "B1 1E 85 F8 C8 B1 1E 85 F9 A5 1C 85 FA A5 1D "
    "85 FB A9 FE 85 FF 20 09 E0 AA D0 D5 60"
)


@dataclass(frozen=True, slots=True)
class HotAsset:
    name: str
    sector: int
    byte_length: int
    sha256: str
    destination: str
    role: str

    @property
    def payload_offset(self) -> int:
        relative_sector = self.sector - TRACK2_START_LBA
        if relative_sector < 0:
            raise ValueError("asset absolute LBA precedes Track 2")
        return relative_sector * SECTOR_BYTES


HOT_ASSETS = (
    HotAsset(
        "main_scene_local_a",
        0x228E,
        7 * SECTOR_BYTES,
        "cfa2098d00ceef753602d7576dc624a697b6eeb2b45d31bfcf74664584a52e23",
        "$4000",
        "local scene data",
    ),
    HotAsset(
        "main_scene_local_b",
        0x22DE,
        3 * SECTOR_BYTES,
        "77781001bbad95259f43101b8117afb4174266019f417c9ca1d5c84b85f5d52e",
        "$9000",
        "local scene data",
    ),
    HotAsset(
        "main_scene_vram",
        0x22E8,
        0xEE00,
        "a91b4539f74520a6ead8f61a14fbde9ebc6ef3a2117ebe661d6c9664f14475fa",
        "VRAM $0900",
        "large scene graphics",
    ),
    HotAsset(
        "alternate_scene_local",
        0x25B8,
        5 * SECTOR_BYTES,
        "252a92c17d03a4cb474996bc638f963bbf021d73dad0f51c4a216193a3a83155",
        "$9000",
        "alternate local scene data",
    ),
    HotAsset(
        "alternate_scene_vram",
        0x25C2,
        0xEE00,
        "4808990453bb9e33c900b5dd22193cd02dd1804ca48ae0dce0c0d8e2ffdd2833",
        "VRAM $0900",
        "alternate large scene graphics",
    ),
    HotAsset(
        "portrait_common",
        0x1458,
        0x2020,
        "1e2cfc1192c332d8169ea0944da015ec8111cd260690203de16023364b8fedf8",
        "VRAM $4000",
        "portrait/UI graphics",
    ),
    HotAsset(
        "portrait_variant",
        0x1561,
        0x2020,
        "531c2f9ed4b3f8000dbf1d38ba2167301964c41c1b17450687bf7ff143fef7b6",
        "VRAM $4000",
        "portrait/UI graphics",
    ),
)


class PackBitsError(ValueError):
    """Raised when a word-PackBits stream is malformed."""


def packbits_words(data: bytes) -> bytes:
    """Encode an even-length byte string as PackBits runs of 16-bit words.

    Control 0..127 is followed by control+1 literal words.
    Control 129..255 is followed by one word repeated 257-control times.
    Control 128 is reserved and never emitted.
    """

    if len(data) % 2:
        raise PackBitsError("word PackBits requires an even byte length")
    words = tuple(data[index : index + 2] for index in range(0, len(data), 2))
    output = bytearray()
    index = 0

    while index < len(words):
        repeat_end = index + 1
        while (
            repeat_end < len(words)
            and words[repeat_end] == words[index]
            and repeat_end - index < 128
        ):
            repeat_end += 1
        repeat_count = repeat_end - index

        if repeat_count >= 3:
            output.append(257 - repeat_count)
            output.extend(words[index])
            index = repeat_end
            continue

        literal_start = index
        index += 1
        while index < len(words) and index - literal_start < 128:
            repeat_end = index + 1
            while (
                repeat_end < len(words)
                and words[repeat_end] == words[index]
                and repeat_end - index < 128
            ):
                repeat_end += 1
            if repeat_end - index >= 3:
                break
            index += 1
        literal_count = index - literal_start
        output.append(literal_count - 1)
        for word in words[literal_start:index]:
            output.extend(word)

    return bytes(output)


def unpackbits_words(encoded: bytes, expected_bytes: int | None = None) -> bytes:
    """Decode :func:`packbits_words` for round-trip and future runtime tests."""

    output = bytearray()
    cursor = 0
    while cursor < len(encoded):
        control = encoded[cursor]
        cursor += 1
        if control <= 127:
            word_count = control + 1
            byte_count = word_count * 2
            end = cursor + byte_count
            if end > len(encoded):
                raise PackBitsError("truncated literal run")
            output.extend(encoded[cursor:end])
            cursor = end
        elif control >= 129:
            repeat_count = 257 - control
            end = cursor + 2
            if end > len(encoded):
                raise PackBitsError("truncated repeat word")
            output.extend(encoded[cursor:end] * repeat_count)
            cursor = end
        else:
            raise PackBitsError("reserved PackBits control 128 is invalid")

    if expected_bytes is not None and len(output) != expected_bytes:
        raise PackBitsError(
            f"decoded {len(output)} bytes; expected {expected_bytes}"
        )
    return bytes(output)


def validate_scene_loaders(payload: bytes) -> dict[str, bool]:
    """Validate the two blocking scene CD_READ wrappers byte-for-byte.

    Both wrappers call System Card CD_READ at $E009, copy the return code to X,
    and immediately branch back to the start on nonzero status. Neither routine
    contains a vertical-sync wait, software countdown, or deliberate delay.
    """

    local_start = MOVEMENT_MODULE_PAYLOAD_BASE + LOCAL_SCENE_LOADER_CPU
    vram_start = MOVEMENT_MODULE_PAYLOAD_BASE + VRAM_SCENE_LOADER_CPU
    return {
        "local_scene_loader": (
            payload[local_start : local_start + len(LOCAL_SCENE_LOADER_BYTES)]
            == LOCAL_SCENE_LOADER_BYTES
        ),
        "vram_scene_loader": (
            payload[vram_start : vram_start + len(VRAM_SCENE_LOADER_BYTES)]
            == VRAM_SCENE_LOADER_BYTES
        ),
    }


def _asset_bytes(payload: bytes, asset: HotAsset) -> bytes:
    blob = payload[
        asset.payload_offset : asset.payload_offset + asset.byte_length
    ]
    if len(blob) != asset.byte_length:
        raise ValueError(f"{asset.name}: source is truncated")
    digest = hashlib.sha256(blob).hexdigest()
    if digest != asset.sha256:
        raise ValueError(
            f"{asset.name}: SHA-256 mismatch: expected {asset.sha256}, got {digest}"
        )
    return blob


def _sectors(byte_count: int) -> int:
    return math.ceil(byte_count / SECTOR_BYTES)


def analyze_hot_assets(payload: bytes) -> dict[str, object]:
    loader_guards = validate_scene_loaders(payload)
    if not all(loader_guards.values()):
        raise ValueError("scene loader source guard mismatch")

    rows = []
    for asset in HOT_ASSETS:
        blob = _asset_bytes(payload, asset)
        packed = packbits_words(blob)
        if unpackbits_words(packed, len(blob)) != blob:
            raise RuntimeError(f"{asset.name}: PackBits round trip failed")
        zlib_size = len(zlib.compress(blob, 9))
        raw_sectors = _sectors(len(blob))
        packed_sectors = _sectors(len(packed))
        rows.append(
            {
                "name": asset.name,
                "absolute_lba": f"0x{asset.sector:04X}",
                "track2_relative_sector": (
                    f"0x{asset.sector - TRACK2_START_LBA:04X}"
                ),
                "payload_offset": f"0x{asset.payload_offset:08X}",
                "destination": asset.destination,
                "role": asset.role,
                "raw_bytes": len(blob),
                "raw_sectors": raw_sectors,
                "packbits_word_bytes": len(packed),
                "packbits_word_ratio_percent": len(packed) / len(blob) * 100.0,
                "packbits_word_sectors": packed_sectors,
                "packbits_word_sectors_saved": raw_sectors - packed_sectors,
                "packbits_word_1x_transfer_seconds": (
                    packed_sectors / CD_SECTORS_PER_SECOND
                ),
                "zlib9_bytes_upper_bound_only": zlib_size,
                "zlib9_ratio_percent_upper_bound_only": (
                    zlib_size / len(blob) * 100.0
                ),
            }
        )

    main = {row["name"]: row for row in rows}
    main_raw_sectors = (
        main["main_scene_local_a"]["raw_sectors"]
        + main["main_scene_local_b"]["raw_sectors"]
        + main["main_scene_vram"]["raw_sectors"]
    )
    main_packbits_sectors = (
        main["main_scene_local_a"]["raw_sectors"]
        + main["main_scene_local_b"]["raw_sectors"]
        + main["main_scene_vram"]["packbits_word_sectors"]
    )

    return {
        "scene_loader_guards": loader_guards,
        "scene_loader_semantics": {
            "local_cpu": "$423B-$4261",
            "vram_cpu": "$4262-$428D",
            "system_card_cd_read": "$E009",
            "retry": "immediate BNE to wrapper start on nonzero CD_READ status",
            "deliberate_wait_loop": False,
        },
        "assets": rows,
        "main_scene_bundle": {
            "source_sectors": ["0x228E", "0x22DE", "0x22E8"],
            "source_start_gaps_sectors": [0x22DE - 0x228E, 0x22E8 - 0x22DE],
            "raw_transfer_sectors": main_raw_sectors,
            "raw_minimum_1x_stream_seconds": (
                main_raw_sectors / CD_SECTORS_PER_SECOND
            ),
            "vram_packbits_transfer_sectors": main_packbits_sectors,
            "vram_packbits_minimum_1x_stream_seconds": (
                main_packbits_sectors / CD_SECTORS_PER_SECOND
            ),
            "pure_transfer_seconds_saved_before_seek_effects": (
                main_raw_sectors - main_packbits_sectors
            )
            / CD_SECTORS_PER_SECOND,
            "layout_target": (
                "duplicate/relocate the three source components into one "
                "contiguous owned CD extent so the loader performs sequential "
                "reads instead of an 80-sector then 10-sector source jump"
            ),
        },
        "limits": {
            "packbits": (
                "Size is real and lossless, but no HuC6280 decoder is activated "
                "yet. Decoder cost must be benchmarked against saved CD time."
            ),
            "zlib": (
                "zlib is reported only as a compression upper-bound comparison; "
                "it is not a proposed game runtime dependency."
            ),
            "relocation": (
                "No constant-fill region is treated as writable ownership. A new "
                "disc extent must be proven/created by the build layout before "
                "any optimized bundle is emitted."
            ),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure hot scene assets for CD-load optimization."
    )
    parser.add_argument("payload", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = args.payload.read_bytes()
    payload_hash = hashlib.sha256(payload).hexdigest()
    if payload_hash != TRACK2_PAYLOAD_SHA256:
        raise ValueError(
            "payload SHA-256 mismatch: "
            f"expected {TRACK2_PAYLOAD_SHA256}, got {payload_hash}"
        )
    report = analyze_hot_assets(payload)
    report["payload_sha256"] = payload_hash
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
