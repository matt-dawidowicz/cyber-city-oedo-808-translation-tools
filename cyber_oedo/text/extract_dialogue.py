"""Versioned facade for the structured dialogue extractor."""

from __future__ import annotations

from cyber_oedo.contracts import DIALOGUE_V1
from cyber_oedo.text import _extract_dialogue_impl as _implementation


_implementation.OUTPUT_FIELDS = DIALOGUE_V1.fields

globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)

OUTPUT_FIELDS = DIALOGUE_V1.fields


if __name__ == "__main__":
    _implementation.main()
