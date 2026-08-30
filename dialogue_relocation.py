"""Compatibility shim for packaged dialogue relocation helpers."""

from __future__ import annotations

from cyber_oedo.text import dialogue_relocation as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
