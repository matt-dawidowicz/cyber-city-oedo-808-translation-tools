"""Compatibility shim for the packaged translation inventory builder."""

from cyber_oedo.text.build_translation_inventory import *  # noqa: F401,F403
from cyber_oedo.text.build_translation_inventory import main


if __name__ == "__main__":
    raise SystemExit(main())
