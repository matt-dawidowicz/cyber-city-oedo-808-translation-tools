"""Provide one stable command for the maintained package surface."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

from cyber_oedo import __version__
from cyber_oedo.registry import COMMANDS, command_by_name


def help_text() -> str:
    """Build deterministic top-level help text."""

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
            if item.group == group:
                lines.append(f"  {item.name:<30} {item.summary}")
        lines.append("")
    lines.extend(
        [
            "Public interface:",
            "  Use the cyber-oedo command or python -m cyber_oedo.",
            "  Implementation modules live only under cyber_oedo.*.",
        ]
    )
    return "\n".join(lines)


def run_command(
    module_name: str,
    arguments: Sequence[str],
) -> int:
    """Import one canonical package command and invoke its argument API."""

    module = importlib.import_module(module_name)
    main_function = getattr(module, "main")
    result = main_function(list(arguments))
    return 0 if result is None else int(result)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a unified toolkit command and return a process status."""

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
    return run_command(command.module, arguments)


def console_main() -> int:
    """Run the console entry point installed by the package."""

    return main()
