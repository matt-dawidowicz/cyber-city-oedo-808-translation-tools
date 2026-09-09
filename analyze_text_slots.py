"""Compatibility shim for packaged text-slot analysis."""

from cyber_oedo.analysis import analyze_text_slots as _implementation
from cyber_oedo.analysis.analyze_text_slots import *  # noqa: F401,F403

main = _implementation.main


def __getattr__(name: str):
    """Forward compatibility lookups not imported by the public star import."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
