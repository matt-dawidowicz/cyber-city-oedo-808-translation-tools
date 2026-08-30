"""Compatibility shim for packaged Stage 1 runtime helpers."""

from __future__ import annotations

from cyber_oedo.experimental import wide_runtime_stage1 as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)
