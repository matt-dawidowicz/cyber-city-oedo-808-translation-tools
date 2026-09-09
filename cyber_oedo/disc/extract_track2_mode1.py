#!/usr/bin/env python3
"""Extract Track 2's 2048-byte Mode 1 payload from a CloneCD IMG."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import tempfile
from collections.abc import Sequence

from cyber_oedo.disc.cdrom_mode1 import MODE1_SYNC
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)


def extract_mode1_payload(
    image_path: pathlib.Path,
    output_path: pathlib.Path,
    *,
    start_lba: int,
    sector_count: int,
) -> tuple[int, str]:
    """Extract contiguous Mode 1 user data with bounded memory use."""

    if start_lba < 0:
        raise ValueError("start_lba must be non-negative")
    if sector_count <= 0:
        raise ValueError("sector_count must be positive")

    required_size = (start_lba + sector_count) * RAW_SECTOR_SIZE
    image_size = image_path.stat().st_size
    if image_size < required_size:
        raise ValueError(
            f"IMG is too short: need at least {required_size:,} bytes, "
            f"found {image_size:,}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    bytes_written = 0
    temporary_name: str | None = None
    try:
        with image_path.open("rb") as source, tempfile.NamedTemporaryFile(
            "wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_name = destination.name
            source.seek(start_lba * RAW_SECTOR_SIZE)
            for relative_sector in range(sector_count):
                raw = source.read(RAW_SECTOR_SIZE)
                if len(raw) != RAW_SECTOR_SIZE:
                    raise ValueError(
                        f"short read at relative sector {relative_sector}: "
                        f"expected {RAW_SECTOR_SIZE}, got {len(raw)}"
                    )
                if raw[: len(MODE1_SYNC)] != MODE1_SYNC:
                    absolute_lba = start_lba + relative_sector
                    raise ValueError(
                        "invalid raw-sector sync at relative sector "
                        f"{relative_sector} (absolute LBA {absolute_lba})"
                    )
                if raw[15] != 1:
                    raise ValueError(
                        "expected Mode 1 at relative sector "
                        f"{relative_sector}, found mode {raw[15]:02X}"
                    )
                payload = raw[
                    MODE1_USER_DATA_OFFSET:
                    MODE1_USER_DATA_OFFSET + SECTOR_SIZE
                ]
                destination.write(payload)
                digest.update(payload)
                bytes_written += len(payload)

        pathlib.Path(temporary_name).replace(output_path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            pathlib.Path(temporary_name).unlink(missing_ok=True)

    return bytes_written, digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    """Build the Track 2 extraction command parser."""

    return argparse.ArgumentParser(
        description=(
            "Extract the verified 2048-byte user-data area from this "
            "game's raw CloneCD Track 2 sectors."
        ),
        epilog=(
            "Example: python extract_track2_mode1.py game.img "
            "track02_mode1_2048.bin"
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run Track 2 extraction with an explicit argument sequence."""

    parser = build_parser()
    parser.add_argument(
        "image",
        type=pathlib.Path,
        help="source 2352-byte-sector .img",
    )
    parser.add_argument(
        "output",
        type=pathlib.Path,
        help="destination payload .bin",
    )
    parser.add_argument(
        "--start-lba",
        type=lambda value: int(value, 0),
        default=TRACK2_START_LBA,
        help=(
            "first raw IMG sector to extract "
            f"(default: {TRACK2_START_LBA})"
        ),
    )
    parser.add_argument(
        "--sector-count",
        type=lambda value: int(value, 0),
        default=TRACK2_SECTOR_COUNT,
        help=(
            "number of Mode 1 sectors "
            f"(default: {TRACK2_SECTOR_COUNT})"
        ),
    )
    args = parser.parse_args(argv)

    try:
        bytes_written, digest = extract_mode1_payload(
            args.image,
            args.output,
            start_lba=args.start_lba,
            sector_count=args.sector_count,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))

    print(f"output={args.output.resolve()}")
    print(f"bytes={bytes_written}")
    print(f"sectors={bytes_written // SECTOR_SIZE}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
