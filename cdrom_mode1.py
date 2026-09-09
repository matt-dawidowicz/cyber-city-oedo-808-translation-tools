"""Compatibility shim for :mod:`cyber_oedo.disc.cdrom_mode1`."""

from cyber_oedo.disc import cdrom_mode1 as _implementation
from cyber_oedo.disc.cdrom_mode1 import *  # noqa: F401,F403
from cyber_oedo.disc.patching import apply_payload_patches


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    if name == "apply_payload_patches":
        return apply_payload_patches
    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))
