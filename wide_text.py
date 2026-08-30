"""Compatibility shim for :mod:`cyber_oedo.text.wide_text`."""

from __future__ import annotations

from cyber_oedo.text import wide_text as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
