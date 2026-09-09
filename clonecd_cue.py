"""Compatibility shim for :mod:`cyber_oedo.disc.clonecd_cue`."""

from cyber_oedo.disc import clonecd_cue as _implementation
from cyber_oedo.disc.clonecd_cue import *  # noqa: F401,F403

main = _implementation.main


def __getattr__(name: str):
    """Forward compatibility lookups to the packaged implementation."""

    return getattr(_implementation, name)


def __dir__() -> list[str]:
    """Expose the union of shim and implementation names."""

    return sorted(set(globals()) | set(dir(_implementation)))


if __name__ == "__main__":
    raise SystemExit(main())
