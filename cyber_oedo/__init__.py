"""Stable package surface for the Cyber City Oedo 808 toolkit."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("cyber-city-oedo-808-translation-tools")
except PackageNotFoundError:
    __version__ = "0+local"


__all__ = ["__version__"]
