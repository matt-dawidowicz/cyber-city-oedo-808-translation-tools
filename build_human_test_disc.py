"""Compatibility shim for :mod:`cyber_oedo.build.human_test`."""

from cyber_oedo.build.human_test import *  # noqa: F401,F403
from cyber_oedo.build.human_test import main


if __name__ == "__main__":
    raise SystemExit(main())
