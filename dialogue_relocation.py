"""Compatibility shim for :mod:`cyber_oedo.text.dialogue_relocation`."""

from cyber_oedo.text import dialogue_relocation as _implementation
from cyber_oedo.text.dialogue_relocation import *  # noqa: F401,F403


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))
