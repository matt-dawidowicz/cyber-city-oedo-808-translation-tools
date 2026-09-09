"""Compatibility shim for :mod:`cyber_oedo.disc.game_layout`."""

from cyber_oedo.disc import game_layout as _implementation
from cyber_oedo.disc.game_layout import *  # noqa: F401,F403


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))
