"""Provide one stable command while preserving every legacy script."""

from __future__ import annotations

import runpy
import sys
from collections.abc import Sequence

from cyber_oedo import __version__
from cyber_oedo.registry import COMMANDS, command_by_name


def help_text() -> str:
    """Build deterministic top-level help text.

    Returns:
        Human-readable command overview grouped by operator role.
    """

    lines = [
        "Cyber City Oedo 808 translation-analysis toolkit",
        "",
        "Usage:",
        "  cyber-oedo <command> [arguments]",
        "  python -m cyber_oedo <command> [arguments]",
        "",
        "Built-in commands:",
        "  doctor                       Check the local tool environment.",
        "",
    ]
    groups = tuple(dict.fromkeys(item.group for item in COMMANDS))
    for group in groups:
        lines.append(f"{group} commands:")
        for item in COMMANDS:
            if item.group != group:
                continue
            lines.append(f"  {item.name:<30} {item.summary}")
        lines.append("")
    lines.extend(
        [
            "Compatibility:",
            "  Existing 'python script.py ...' invocations remain supported.",
            "  Subcommand arguments are forwarded unchanged to each script.",
        ]
    )
    return "\n".join(lines)


def run_script(module: str, arguments: Sequence[str]) -> int:
    """Execute one existing script module with forwarded arguments.

    Args:
        module: Top-level module name registered for the command.
        arguments: Arguments that should become the script's ``sys.argv``.

    Returns:
        Zero when the script returns normally.

    Side Effects:
        Temporarily replaces ``sys.argv`` and executes the module as
        ``__main__``. The original argument vector is always restored.
    """

    original_argv = sys.argv
    try:
        sys.argv = [f"{module}.py", *arguments]
        runpy.run_module(module, run_name="__main__")
    finally:
        sys.argv = original_argv
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a unified toolkit command.

    Args:
        argv: Optional argument sequence excluding the executable name.

    Returns:
        Process-style status code. Script-level ``SystemExit`` exceptions are
        intentionally allowed to propagate so existing argparse behavior is
        preserved.
    """

    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        print(help_text())
        return 0
    if arguments[0] in {"-V", "--version"}:
        print(__version__)
        return 0
    if arguments[0] == "doctor":
        from cyber_oedo.doctor import main as doctor_main

        return doctor_main(arguments[1:])

    command_name = arguments.pop(0)
    command = command_by_name(command_name)
    if command is None:
        print(f"error: unknown command: {command_name}", file=sys.stderr)
        print("", file=sys.stderr)
        print(help_text(), file=sys.stderr)
        return 2
    return run_script(command.module, arguments)


def console_main() -> int:
    """Run the console entry point installed by the package.

    Returns:
        Process-style status code from :func:`main`.
    """

    return main()
