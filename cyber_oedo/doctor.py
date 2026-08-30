"""Check whether a local installation can run the maintained tool surface."""

from __future__ import annotations

import importlib.util
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from cyber_oedo.registry import script_modules


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """Represent one environment check and its severity.

    Args:
        level: ``ok``, ``warn``, or ``fail``.
        label: Short check name.
        detail: Human-readable result detail.
    """

    level: str
    label: str
    detail: str


def python_check() -> DoctorCheck:
    """Check the supported Python version floor.

    Returns:
        Passing check for Python 3.11 or newer, otherwise a failure.
    """

    current = sys.version_info[:3]
    detail = platform.python_version()
    if current >= (3, 11, 0):
        return DoctorCheck("ok", "Python", detail)
    return DoctorCheck("fail", "Python", f"{detail}; Python 3.11+ required")


def module_check() -> DoctorCheck:
    """Check that every registered legacy command module is importable.

    Returns:
        Passing check when every registered script module can be located.
    """

    missing = [
        module
        for module in script_modules()
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        count = len(script_modules())
        return DoctorCheck("ok", "Command modules", f"{count} available")
    return DoctorCheck(
        "fail",
        "Command modules",
        "missing: " + ", ".join(missing),
    )


def pillow_check() -> DoctorCheck:
    """Check the optional Pillow dependency used by graphics commands.

    Returns:
        Passing check when Pillow is installed, otherwise a warning.
    """

    if importlib.util.find_spec("PIL") is not None:
        return DoctorCheck("ok", "Pillow", "available")
    return DoctorCheck(
        "warn",
        "Pillow",
        "not installed; graphics commands require the 'graphics' extra",
    )


def collect_checks() -> tuple[DoctorCheck, ...]:
    """Collect all environment checks in display order.

    Returns:
        Immutable sequence of core and optional dependency checks.
    """

    return python_check(), module_check(), pillow_check()


def main(argv: Sequence[str] | None = None) -> int:
    """Print local environment checks.

    Args:
        argv: Reserved argument sequence. No doctor options are defined yet.

    Returns:
        One when a core check fails, otherwise zero. Warnings are non-fatal.
    """

    arguments = list(argv or ())
    if arguments:
        print("doctor does not accept arguments", file=sys.stderr)
        return 2

    checks = collect_checks()
    for check in checks:
        print(f"[{check.level}] {check.label}: {check.detail}")
    return 1 if any(check.level == "fail" for check in checks) else 0
