"""Compatibility shim for the packaged inventory builder."""

from __future__ import annotations

from cyber_oedo.text import build_translation_inventory as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
