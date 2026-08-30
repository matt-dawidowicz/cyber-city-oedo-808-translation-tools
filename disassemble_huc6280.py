"""Compatibility shim for the packaged HuC6280 disassembler."""

from __future__ import annotations

from cyber_oedo.analysis import disassemble_huc6280 as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
