"""Compatibility shim for :mod:`cyber_oedo.graphics.title_logo_mask`."""

from cyber_oedo.graphics import title_logo_mask as _implementation
from cyber_oedo.graphics.title_logo_mask import *  # noqa: F401,F403


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))
