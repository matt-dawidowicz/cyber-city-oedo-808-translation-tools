"""Compatibility shim for the packaged structural scanner."""

from __future__ import annotations

from cyber_oedo.analysis import scan_track as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
