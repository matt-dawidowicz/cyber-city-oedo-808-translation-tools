"""Disassemble only the requested HuC6280 byte range from disk."""

from __future__ import annotations

from collections.abc import Sequence

from cyber_oedo.analysis.disassemble_huc6280 import (
    build_parser,
    linear_disassemble,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Read the requested region directly instead of the complete binary."""

    args = build_parser().parse_args(argv)
    file_size = args.binary.stat().st_size
    end = args.offset + args.length
    if end > file_size:
        raise ValueError(
            f"requested region ends at 0x{end:X}; "
            f"file size is 0x{file_size:X}"
        )
    with args.binary.open("rb") as source:
        source.seek(args.offset)
        region = source.read(args.length)
    if len(region) != args.length:
        raise ValueError(
            f"short read: expected {args.length} bytes, "
            f"found {len(region)}"
        )
    for instruction in linear_disassemble(
        region,
        args.offset,
        args.address,
    ):
        print(instruction.format())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
