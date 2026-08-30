"""Versioned facade for the translator-facing inventory builder."""

from __future__ import annotations

from cyber_oedo.contracts import TRANSLATION_INVENTORY_V1
from cyber_oedo.text import (
    _build_translation_inventory_impl as _implementation,
)


_implementation.OUTPUT_FIELDS = TRANSLATION_INVENTORY_V1.fields

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)

OUTPUT_FIELDS = TRANSLATION_INVENTORY_V1.fields


if __name__ == "__main__":
    _implementation.main()
