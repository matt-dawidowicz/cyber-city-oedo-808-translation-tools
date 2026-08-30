"""Compatibility shim for the packaged title-screen generator."""

from __future__ import annotations

from cyber_oedo.graphics import title_screen as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
