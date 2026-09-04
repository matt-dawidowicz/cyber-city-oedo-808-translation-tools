"""Extract Track 2's 2048-byte Mode 1 payload from a CloneCD IMG."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import tempfile

from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    TRACK2_SECTOR_COUNT,
    TRACK2_START_LBA,
)

MODE1_SYNC = b"\x00" + (b"\xFF" * 10) + b"\x00"


def extract_mode1_payload(
    image_path: pathlib.Path,
    output_path: pathlib.Path,
    *,
    start_lba: int,
    sector_count: int,
) -> tuple[int, str]:
    """Extract a contiguous range of structurally valid Mode 1 user data."""

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
                    raise ValueError(
                        "invalid raw-sector sync at relative sector "
                        f"{relative_sector}"
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
    """Build the extraction command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Extract 2048-byte user data from this game's raw CloneCD "
            "Track 2 Mode 1 sectors."
        )
    )
    parser.add_argument("image", type=pathlib.Path, help="source raw .img")
    parser.add_argument("output", type=pathlib.Path, help="destination .bin")
    parser.add_argument(
        "--start-lba",
        type=lambda value: int(value, 0),
        default=TRACK2_START_LBA,
    )
    parser.add_argument(
        "--sector-count",
        type=lambda value: int(value, 0),
        default=TRACK2_SECTOR_COUNT,
    )
    return parser


def main() -> None:
    """Run Track 2 extraction and print output identity information."""

    parser = build_parser()
    args = parser.parse_args()
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


if __name__ == "__main__":
    main()
