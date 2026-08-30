"""Compatibility shim for the packaged Track 2 extractor."""

from __future__ import annotations

from cyber_oedo.disc import extract_track2_mode1 as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
