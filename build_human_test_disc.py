"""Compatibility shim for the decomposed authenticated build facade."""

from __future__ import annotations

from cyber_oedo.build import human_test as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
