"""Compatibility shim for the packaged Track 2 extractor."""

from cyber_oedo.disc import extract_track2_mode1 as _implementation
from cyber_oedo.disc.extract_track2_mode1 import *  # noqa: F401,F403

main = _implementation.main


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
