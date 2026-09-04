"""Regression tests for the package-only restart command surface."""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import pathlib
import sys
import tomllib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    """Keep the distribution free of legacy root Python modules."""

    def test_pyproject_uses_package_discovery_only(self) -> None:
        """Do not reinstall deleted compatibility shims as py-modules."""

        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        setuptools = metadata["tool"]["setuptools"]
        self.assertNotIn("py-modules", setuptools)
        self.assertIn(
            "cyber_oedo*",
            setuptools["packages"]["find"]["include"],
        )

    def test_registered_command_modules_are_importable(self) -> None:
        """Require every command to import from the installed package."""

        from cyber_oedo.registry import command_modules

        for module in command_modules():
            self.assertTrue(module.startswith("cyber_oedo."))
            self.assertIsNotNone(importlib.util.find_spec(module))
            self.assertIsNotNone(importlib.import_module(module))


class CommandTests(unittest.TestCase):
    """Verify restart help and package-module dispatch."""

    def test_help_excludes_removed_build_surface(self) -> None:
        """Do not advertise the abandoned human-test builder."""

        from cyber_oedo import cli

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main(["--help"])
        text = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("extract-dialogue", text)
        self.assertNotIn("build-human-test-disc", text)
        self.assertNotIn("build-wide-engine-stage1", text)

    def test_arguments_are_forwarded_to_package_module(self) -> None:
        """Dispatch directly to the canonical package implementation."""

        from cyber_oedo import cli

        original = sys.argv
        observed: list[str] = []

        def fake_run_module(module: str, *, run_name: str) -> None:
            """Capture dispatch state instead of running the command."""

            self.assertEqual(module, "cyber_oedo.text.extract_dialogue")
            self.assertEqual(run_name, "__main__")
            observed.extend(sys.argv)

        with mock.patch.object(cli.runpy, "run_module", fake_run_module):
            status = cli.main(
                ["extract-dialogue", "input.bin", "dialogue.tsv"]
            )
        self.assertEqual(status, 0)
        self.assertEqual(
            observed,
            [
                "cyber_oedo.text.extract_dialogue",
                "input.bin",
                "dialogue.tsv",
            ],
        )
        self.assertIs(sys.argv, original)


if __name__ == "__main__":
    unittest.main()
