"""Compatibility shim for the packaged Stage 1 runtime helpers."""

from cyber_oedo.experimental import wide_runtime_stage1 as _implementation
from cyber_oedo.experimental.wide_runtime_stage1 import *  # noqa: F401,F403


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))
