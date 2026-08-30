"""Compatibility shim for :mod:`cyber_oedo.disc.clonecd_cue`."""

from __future__ import annotations

from cyber_oedo.disc import clonecd_cue as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
