"""Compatibility shim for the packaged PC Engine tile renderer."""

from __future__ import annotations

from cyber_oedo.graphics import render_pce_tiles as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
