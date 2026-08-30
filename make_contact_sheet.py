"""Compatibility shim for the packaged contact-sheet generator."""

from __future__ import annotations

from cyber_oedo.graphics import make_contact_sheet as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
