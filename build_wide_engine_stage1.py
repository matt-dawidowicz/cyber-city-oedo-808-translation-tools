"""Compatibility shim for the packaged Stage 1 build command."""

from __future__ import annotations

from cyber_oedo.experimental import build_wide_engine_stage1 as _implementation


globals().update(
    {
        name: value
        for name, value in vars(_implementation).items()
        if not name.startswith("__")
    }
)


if __name__ == "__main__":
    _implementation.main()
