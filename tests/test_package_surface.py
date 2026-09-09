"""Regression tests for the installable package and command surface."""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import pathlib
import tomllib
import unittest
from unittest import mock

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPOSITORY_ROOT / "cyber_oedo"


def package_python_paths() -> list[pathlib.Path]:
    """Return package Python files recursively in deterministic order."""

    return sorted(PACKAGE_ROOT.rglob("*.py"))


class PackageSourceTests(unittest.TestCase):
    """Keep the package compatible with the repository style contract."""

    def test_package_nodes_have_docstrings(self) -> None:
        """Require module, class, and function docstrings in package files."""

        failures: list[str] = []
        node_types = (
            ast.Module,
            ast.ClassDef,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
        )
        for path in package_python_paths():
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
        """Keep package source lines within the 79-column rule."""

        failures: list[str] = []
        for path in package_python_paths():
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if len(line) > 79:
                    failures.append(
                        f"{path.name}:{number}:{len(line)}"
                    )
        self.assertEqual([], failures)


class PackagingMetadataTests(unittest.TestCase):
    """Keep distribution metadata aligned with the command registry."""

    def test_registered_commands_are_included_as_py_modules(self) -> None:
        """Require every legacy command in the built distribution."""

        from cyber_oedo.registry import script_modules

        pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
        metadata = tomllib.loads(
            pyproject_path.read_text(encoding="utf-8")
        )
        packaged = set(
            metadata["tool"]["setuptools"]["py-modules"]
        )
        missing = set(script_modules()) - packaged
        self.assertEqual(set(), missing)

    def test_package_discovery_accepts_future_subpackages(self) -> None:
        """Require recursive discovery for package namespaces."""

        pyproject_path = REPOSITORY_ROOT / "pyproject.toml"
        metadata = tomllib.loads(
            pyproject_path.read_text(encoding="utf-8")
        )
        setuptools = metadata["tool"]["setuptools"]
        patterns = setuptools["packages"]["find"]["include"]
        self.assertIn("cyber_oedo*", patterns)


class UnifiedCommandTests(unittest.TestCase):
    """Verify registry completeness and compatibility dispatch behavior."""

    def test_registered_script_modules_are_locatable(self) -> None:
        """Require every legacy command module to remain importable."""

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

    def test_direct_arguments_are_forwarded_unchanged(self) -> None:
        """Pass pipeline arguments directly without global argv mutation."""

        from cyber_oedo import cli

        target = mock.Mock()
        target.main.return_value = 0
        with mock.patch.object(
            cli.importlib,
            "import_module",
            return_value=target,
        ) as importer:
            status = cli.main(
                [
                    "extract-dialogue",
                    "input.bin",
                    "dialogue.tsv",
                ]
            )
        self.assertEqual(status, 0)
        importer.assert_called_once_with(
            "cyber_oedo.text.extract_dialogue"
        )
        target.main.assert_called_once_with(
            ["input.bin", "dialogue.tsv"]
        )

    def test_legacy_fallback_uses_child_interpreter(self) -> None:
        """Keep old diagnostics isolated from process-global argv."""

        from cyber_oedo import cli

        completed = mock.Mock(returncode=7)
        with mock.patch.object(
            cli.subprocess,
            "run",
            return_value=completed,
        ) as runner:
            status = cli.main(
                ["clonecd-cue", "input.ccd"]
            )
        self.assertEqual(status, 7)
        command = runner.call_args.args[0]
        self.assertEqual(command[-2:], ["clonecd_cue", "input.ccd"])
        self.assertFalse(runner.call_args.kwargs["check"])


if __name__ == "__main__":
    unittest.main()
