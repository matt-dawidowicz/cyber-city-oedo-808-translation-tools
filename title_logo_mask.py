"""Compatibility shim for the packaged title-logo mask."""

from __future__ import annotations

from cyber_oedo.graphics import title_logo_mask as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
