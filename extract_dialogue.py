"""Compatibility shim for the packaged dialogue extractor."""

from __future__ import annotations

from cyber_oedo.text import extract_dialogue as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
