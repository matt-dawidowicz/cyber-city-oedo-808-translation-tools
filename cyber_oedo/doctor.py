"""Check whether a local installation can run the maintained tool surface."""

from __future__ import annotations

import importlib.util
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from cyber_oedo.registry import command_modules


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """Represent one environment check and its severity."""

    level: str
    label: str
    detail: str


def python_check() -> DoctorCheck:
    """Check the supported Python version floor."""

    current = sys.version_info[:3]
    detail = platform.python_version()
    if current >= (3, 11, 0):
        return DoctorCheck("ok", "Python", detail)
    return DoctorCheck("fail", "Python", f"{detail}; Python 3.11+ required")


def module_check() -> DoctorCheck:
    """Check that every registered command module is importable."""

    modules = command_modules()
    missing = [
        module
        for module in modules
        if importlib.util.find_spec(module) is None
    ]
    if not missing:
        return DoctorCheck(
            "ok",
            "Command modules",
            f"{len(modules)} available",
        )
    return DoctorCheck(
        "fail",
        "Command modules",
        "missing: " + ", ".join(missing),
    )


def pillow_check() -> DoctorCheck:
    """Check the optional Pillow dependency used by graphics commands."""

    if importlib.util.find_spec("PIL") is not None:
        return DoctorCheck("ok", "Pillow", "available")
    return DoctorCheck(
        "warn",
        "Pillow",
        "not installed; graphics commands require the 'graphics' extra",
    )


def collect_checks() -> tuple[DoctorCheck, ...]:
    """Collect all environment checks in display order."""

    return python_check(), module_check(), pillow_check()


def main(argv: Sequence[str] | None = None) -> int:
    """Print local environment checks."""

    arguments = list(argv or ())
    if arguments:
        print("doctor does not accept arguments", file=sys.stderr)
        return 2

    checks = collect_checks()
    for check in checks:
        print(f"[{check.level}] {check.label}: {check.detail}")
    return 1 if any(check.level == "fail" for check in checks) else 0
