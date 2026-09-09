"""Provide one stable command without mutating process-global argv."""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Sequence

from cyber_oedo import __version__
from cyber_oedo.registry import COMMANDS, command_by_name

DIRECT_COMMANDS = {
    "extract-track2-mode1": (
        "cyber_oedo.disc.extract_track2_mode1"
    ),
    "scan-track": "cyber_oedo.analysis.scan_track",
    "build-resource-map": "cyber_oedo.analysis.build_resource_map",
    "scan-likely-sjis": "cyber_oedo.analysis.scan_likely_sjis",
    "extract-dialogue": "cyber_oedo.text.extract_dialogue",
    "extract-auxiliary-text": (
        "cyber_oedo.text.extract_auxiliary_text"
    ),
    "build-translation-inventory": (
        "cyber_oedo.text.build_translation_inventory"
    ),
    "validate-translation-inventory": (
        "cyber_oedo.text.validate_translation_inventory"
    ),
    "analyze-text-slots": (
        "cyber_oedo.analysis.analyze_text_slots"
    ),
    "build-human-test-disc": "cyber_oedo.build.human_test",
    "build-analysis-db": "cyber_oedo.analysis.build_analysis_db",
    "describe-contracts": "cyber_oedo.commands.describe_contracts",
    "plan-human-test": "cyber_oedo.commands.plan_human_test",
    "inventory-summary": "cyber_oedo.commands.inventory_summary",
    "disassemble-huc6280": "cyber_oedo.commands.disassemble_region",
    "prove-dialogue-runtime": (
        "cyber_oedo.runtime.dialogue_interpreter"
    ),
    "scan-reversed-sjis": "cyber_oedo.analysis.scan_reversed_sjis",
}


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
            if item.group != group:
                continue
            lines.append(f"  {item.name:<30} {item.summary}")
        lines.append("")
    lines.extend(
        [
            "Compatibility:",
            "  Existing 'python script.py ...' invocations remain supported.",
            "  Pipeline commands dispatch directly into package APIs.",
        ]
    )
    return "\n".join(lines)


def _run_direct(
    module_name: str,
    arguments: Sequence[str],
) -> int:
    """Import a package command and call its explicit argument API."""

    module = importlib.import_module(module_name)
    main_function = getattr(module, "main")
    result = main_function(list(arguments))
    return 0 if result is None else int(result)


def _run_legacy(
    module_name: str,
    arguments: Sequence[str],
) -> int:
    """Isolate an unchanged legacy diagnostic in a child interpreter."""

    completed = subprocess.run(
        [sys.executable, "-m", module_name, *arguments],
        check=False,
    )
    return completed.returncode


def run_command(
    command_name: str,
    module_name: str,
    arguments: Sequence[str],
) -> int:
    """Dispatch directly when an explicit package entry point exists."""

    direct_module = DIRECT_COMMANDS.get(command_name)
    if direct_module is not None:
        return _run_direct(direct_module, arguments)
    return _run_legacy(module_name, arguments)


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
        print(
            f"error: unknown command: {command_name}",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print(help_text(), file=sys.stderr)
        return 2
    return run_command(
        command_name,
        command.module,
        arguments,
    )


def console_main() -> int:
    """Run the console entry point installed by the package."""

    return main()
