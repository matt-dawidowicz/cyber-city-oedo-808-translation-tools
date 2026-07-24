#!/usr/bin/env python3
"""Extract Track 2's 2048-byte Mode 1 payload from the supplied CloneCD IMG.

The CloneCD ``.img`` stores 2352-byte raw sectors.  All other tools in this
directory expect a flat file containing only the 2048-byte user-data portion
of each valid Track 2 Mode 1 sector.  This command creates that intermediate
file without touching the source image.

This is an extractor, not a raw-sector validator or rebuilder.  It verifies the
12-byte sync pattern and mode byte for every selected sector, but it does not
recalculate or authenticate EDC/ECC fields.  A future patcher must recalculate
those fields when reinserting modified payload bytes.

The defaults are specific to this game's supplied disc image.  Override them
only when deliberately examining another dump or a corrected layout.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import tempfile

from game_layout import (
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
    """Extract a contiguous range of Mode 1 user-data sectors.

    Output is first written to a temporary file beside the destination and is
    moved into place only after every source sector passes structural checks.
    This avoids leaving an apparently valid but truncated payload after an
    invalid sector or interrupted read.

    Args:
        image_path: Source CloneCD IMG containing 2352-byte raw sectors.
        output_path: Destination for concatenated 2048-byte user-data sectors.
        start_lba: Zero-based raw-sector index at which extraction begins.
        sector_count: Number of consecutive Mode 1 sectors to extract.

    Returns:
        A tuple containing the number of payload bytes written and the
        lowercase hexadecimal SHA-256 digest of those bytes.

    Raises:
        OSError: If source metadata cannot be read, source or temporary files
            cannot be opened, bytes cannot be written, or the final atomic
            replacement fails.
        ValueError: If ``start_lba`` is negative, ``sector_count`` is not
            positive, the image is too short, a sector read is incomplete,
            a sync pattern is invalid, or a selected sector is not Mode 1.

    Side Effects:
        Creates ``output_path.parent`` when needed. Writes a temporary file
        in that directory and atomically replaces ``output_path`` only after
        successful validation. Removes the temporary file after a failure.

    Notes:
        Structural checks cover the 12-byte sync pattern and mode byte. The
        routine deliberately does not verify EDC/ECC or BCD address fields.
        The source image is opened read-only and is never modified.
    """

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
                        f"{relative_sector} "
                        f"(absolute LBA {start_lba + relative_sector})"
                    )
                if raw[15] != 1:
                    raise ValueError(
                        "expected Mode 1 at relative sector "
                        f"{relative_sector}, "
                        f"found mode {raw[15]:02X}"
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
    """Build the command-line argument parser.

    Returns:
        A parser containing the program description and usage example. Input
        and option arguments are added by ``main``.

    Notes:
        Keeping parser construction separate allows tests and documentation
        tools to inspect command metadata without performing file I/O.
    """

    return argparse.ArgumentParser(
        description=(
            "Extract the verified 2048-byte user-data area from this game's "
            "raw CloneCD Track 2 sectors."
        ),
        epilog=(
            "Example: python extract_track2_mode1.py game.img "
            "track02_mode1_2048.bin"
        ),
    )


def main() -> None:
    """Run the Track 2 extraction command.

    Inputs:
        Parses a source IMG path, output path, starting LBA, and sector count
        from command-line arguments.

    Outputs:
        Prints the resolved output path, byte count, sector count, and SHA-256
        digest to standard output.

    Side Effects:
        Calls ``extract_mode1_payload``, which creates directories and writes
        or replaces the requested output file.

    Failure Conditions:
        ``argparse`` exits with status 2 for invalid arguments or for any
        ``OSError`` or ``ValueError`` raised by extraction.
    """

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
        help=f"first raw IMG sector to extract (default: {TRACK2_START_LBA})",
    )
    parser.add_argument(
        "--sector-count",
        type=lambda value: int(value, 0),
        default=TRACK2_SECTOR_COUNT,
        help=f"number of Mode 1 sectors (default: {TRACK2_SECTOR_COUNT})",
    )
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
