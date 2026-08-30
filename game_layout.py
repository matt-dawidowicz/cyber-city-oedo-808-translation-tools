"""Compatibility shim for :mod:`cyber_oedo.disc.game_layout`."""

from __future__ import annotations

from cyber_oedo.disc import game_layout as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
