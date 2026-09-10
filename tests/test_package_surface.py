"""Regression tests for the installable package and command surface."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import tomllib
import unittest
from unittest import mock

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


class PackagingMetadataTests(unittest.TestCase):
    """Keep distribution metadata aligned with the package architecture."""

    def test_package_discovery_accepts_future_subpackages(self) -> None:
        """Require recursive discovery for package namespaces."""

        metadata = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )
        setuptools = metadata["tool"]["setuptools"]
        patterns = setuptools["packages"]["find"]["include"]
        self.assertIn("cyber_oedo*", patterns)

    def test_registered_commands_use_package_modules(self) -> None:
        """Require every maintained command to resolve under cyber_oedo."""

        from cyber_oedo.registry import COMMANDS

        failures = []
        for command in COMMANDS:
            if not command.module.startswith("cyber_oedo."):
                failures.append(command.module)
                continue
            if importlib.util.find_spec(command.module) is None:
                failures.append(command.module)
        self.assertEqual([], failures)


class UnifiedCommandTests(unittest.TestCase):
    """Verify registry completeness and direct package dispatch."""

    def test_help_returns_success(self) -> None:
        """Print top-level usage without importing command modules."""

        from cyber_oedo import cli

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main(["--help"])
        self.assertEqual(status, 0)
        self.assertIn("build-human-test-disc", output.getvalue())
        self.assertIn("doctor", output.getvalue())
        self.assertNotIn("build-wide-engine-stage1", output.getvalue())

    def test_unknown_command_returns_usage_error(self) -> None:
        """Return status two and identify an unknown command."""

        from cyber_oedo import cli

        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            status = cli.main(["not-a-command"])
        self.assertEqual(status, 2)
        self.assertIn("unknown command", output.getvalue())

    def test_arguments_are_forwarded_unchanged(self) -> None:
        """Pass arguments directly to the canonical package module."""

        from cyber_oedo import cli

        target = mock.Mock()
        target.main.return_value = 0
        with mock.patch.object(
            cli.importlib,
            "import_module",
            return_value=target,
        ) as importer:
            status = cli.main(
                ["extract-dialogue", "input.bin", "dialogue.tsv"]
            )
        self.assertEqual(status, 0)
        importer.assert_called_once_with(
            "cyber_oedo.text.extract_dialogue"
        )
        target.main.assert_called_once_with(
            ["input.bin", "dialogue.tsv"]
        )


if __name__ == "__main__":
    unittest.main()
