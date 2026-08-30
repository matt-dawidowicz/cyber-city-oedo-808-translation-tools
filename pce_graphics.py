"""Compatibility shim for :mod:`cyber_oedo.graphics.pce_graphics`."""

from __future__ import annotations

from cyber_oedo.graphics import pce_graphics as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
