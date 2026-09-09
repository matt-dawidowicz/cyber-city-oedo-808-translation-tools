"""Compatibility shim for packaged HuC6280 disassembly helpers."""

from cyber_oedo.analysis import disassemble_huc6280 as _implementation
from cyber_oedo.analysis.disassemble_huc6280 import *  # noqa: F401,F403
from cyber_oedo.commands.disassemble_region import main


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    if name == "main":
        return main
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
