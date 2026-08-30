"""Compatibility shim for :mod:`cyber_oedo.disc.cdrom_mode1`."""

from __future__ import annotations

from cyber_oedo.disc import cdrom_mode1 as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
