"""Compatibility command for bounded HuC6280 region disassembly."""

from __future__ import annotations

from collections.abc import Sequence

from cyber_oedo.analysis.disassemble_huc6280 import main as _analysis_main


def main(argv: Sequence[str] | None = None) -> int:
    """Delegate to the canonical bounded-range disassembler."""

    return _analysis_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
