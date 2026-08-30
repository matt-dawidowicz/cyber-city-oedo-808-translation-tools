"""Regression tests for the installable package and unified command surface."""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "cyber_oedo"


class PackageSourceTests(unittest.TestCase):
    """Keep the new package compatible with the repository style contract."""

    def test_package_nodes_have_docstrings(self) -> None:
        """Require module, class, and function docstrings in package files."""

        failures: list[str] = []
        node_types = (
            ast.Module,
            ast.ClassDef,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        )
        for path in sorted(PACKAGE_ROOT.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                needs_docstring = isinstance(node, node_types)
                if needs_docstring and ast.get_docstring(node) is None:
                    failures.append(
                        f"{path.name}:{getattr(node, 'lineno', 1)}"
                    )
        self.assertEqual([], failures)

    def test_package_lines_fit_pep8_limit(self) -> None:
        """Keep package source lines within the repository's 79-column rule."""

        failures: list[str] = []
        for path in sorted(PACKAGE_ROOT.glob("*.py")):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if len(line) > 79:
                    failures.append(f"{path.name}:{number}:{len(line)}")
        self.assertEqual([], failures)


class UnifiedCommandTests(unittest.TestCase):
    """Verify registry completeness and compatibility dispatch behavior."""

    def test_registered_script_modules_are_locatable(self) -> None:
        """Require every unified script command to resolve to a module."""

        from cyber_oedo.registry import script_modules

        missing = [
            module
            for module in script_modules()
            if importlib.util.find_spec(module) is None
        ]
        self.assertEqual([], missing)

    def test_help_returns_success(self) -> None:
        """Print top-level usage without importing game-specific modules."""

        from cyber_oedo import cli

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("build-human-test-disc", output.getvalue())
        self.assertIn("doctor", output.getvalue())

    def test_unknown_command_returns_usage_error(self) -> None:
        """Return status two and identify an unknown command."""

        from cyber_oedo import cli

        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = cli.main(["not-a-command"])
        self.assertEqual(status, 2)
        self.assertIn("unknown command", output.getvalue())

    def test_script_arguments_are_forwarded_unchanged(self) -> None:
        """Preserve the selected legacy script's complete argument vector."""

        from cyber_oedo import cli

        original = sys.argv
        observed: list[str] = []

        def fake_run_module(module: str, *, run_name: str) -> None:
            """Capture dispatch state without executing the target module."""

            self.assertEqual(module, "extract_dialogue")
            self.assertEqual(run_name, "__main__")
            observed.extend(sys.argv)

        with mock.patch.object(cli.runpy, "run_module", fake_run_module):
            status = cli.main(
                ["extract-dialogue", "input.bin", "dialogue.tsv"]
            )
        self.assertEqual(status, 0)
        self.assertEqual(
            observed,
            ["extract_dialogue.py", "input.bin", "dialogue.tsv"],
        )
        self.assertIs(sys.argv, original)


if __name__ == "__main__":
    unittest.main()
