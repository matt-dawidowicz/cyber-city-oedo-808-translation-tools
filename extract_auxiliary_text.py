"""Compatibility shim for the packaged auxiliary-text extractor."""

from cyber_oedo.text import extract_auxiliary_text as _implementation
from cyber_oedo.text.extract_auxiliary_text import *  # noqa: F401,F403

main = _implementation.main


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
