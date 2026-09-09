"""Compatibility shim for :mod:`cyber_oedo.text.extract_dialogue`."""

from cyber_oedo.text.extract_dialogue import *  # noqa: F401,F403
from cyber_oedo.text.extract_dialogue import main


if __name__ == "__main__":
    raise SystemExit(main())
