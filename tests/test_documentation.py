"""Enforce the repository's Python documentation and formatting baseline.

These tests inspect source syntax rather than runtime game data. They keep the
maintenance contract executable: every module, class, and function must have a
PEP 257-style docstring, Python lines must respect PEP 8's 79-character limit,
and explanatory comments must use the conventional ``# `` prefix.
"""

from __future__ import annotations

import ast
import inspect
import io
import pathlib
import tokenize
import unittest
from collections.abc import Iterator


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]


def python_paths() -> list[pathlib.Path]:
    """Return tracked-source candidates in deterministic path order.

    Returns:
        Root-level Python programs and Python tests, sorted by repository-
        relative POSIX path.

    Notes:
        The repository intentionally uses a flat script layout. Limiting the
        search to the root and ``tests`` avoids virtual environments or local
        generated directories that may exist beside the checkout.
    """

    paths = list(REPOSITORY_ROOT.glob("*.py"))
    paths.extend((REPOSITORY_ROOT / "tests").glob("*.py"))
    return sorted(
        paths,
        key=lambda path: path.relative_to(REPOSITORY_ROOT).as_posix(),
    )


def documented_nodes(tree: ast.AST) -> Iterator[ast.AST]:
    """Yield syntax nodes that require PEP 257 docstrings.

    Args:
        tree: Parsed Python abstract syntax tree.

    Yields:
        The module plus every class, synchronous function, and asynchronous
        function at any nesting depth.
    """

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Module,
                ast.ClassDef,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            yield node


def node_name(node: ast.AST) -> str:
    """Return a stable human-readable name for a documented syntax node.

    Args:
        node: Module, class, or function syntax node.

    Returns:
        ``"<module>"`` for a module or the node's declared ``name``.
    """

    return "<module>" if isinstance(node, ast.Module) else node.name


class DocumentationStandardsTests(unittest.TestCase):
    """Check docstring presence, summary form, lines, and comment prefixes."""

    def test_every_documentable_node_has_a_docstring(self) -> None:
        """Require docstrings on every module, class, and function."""

        failures: list[str] = []
        for path in python_paths():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in documented_nodes(tree):
                if ast.get_docstring(node, clean=False) is None:
                    relative = path.relative_to(REPOSITORY_ROOT)
                    line = getattr(node, "lineno", 1)
                    failures.append(
                        f"{relative}:{line}: {node_name(node)}"
                    )
        self.assertEqual(
            [],
            failures,
            "Missing docstrings:\n" + "\n".join(failures),
        )

    def test_docstring_summaries_follow_pep257_shape(self) -> None:
        """Require concise punctuated summaries and blank separation."""

        failures: list[str] = []
        for path in python_paths():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in documented_nodes(tree):
                raw_docstring = ast.get_docstring(node, clean=False)
                if raw_docstring is None:
                    continue
                lines = inspect.cleandoc(raw_docstring).splitlines()
                relative = path.relative_to(REPOSITORY_ROOT)
                location = (
                    f"{relative}:{getattr(node, 'lineno', 1)}:"
                    f" {node_name(node)}"
                )
                if not lines or not lines[0].strip():
                    failures.append(f"{location}: empty summary")
                    continue
                if len(lines[0]) > 79:
                    failures.append(
                        f"{location}: summary exceeds 79 characters"
                    )
                if lines[0][-1] not in ".?!":
                    failures.append(f"{location}: summary lacks punctuation")
                if len(lines) > 1 and lines[1].strip():
                    failures.append(
                        f"{location}: no blank line after summary"
                    )
        self.assertEqual(
            [],
            failures,
            "Invalid PEP 257 summary shape:\n" + "\n".join(failures),
        )

    def test_python_lines_do_not_exceed_pep8_limit(self) -> None:
        """Reject Python source lines longer than 79 characters."""

        failures: list[str] = []
        for path in python_paths():
            relative = path.relative_to(REPOSITORY_ROOT)
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if len(line) > 79:
                    failures.append(
                        f"{relative}:{line_number}: {len(line)} characters"
                    )
        self.assertEqual(
            [],
            failures,
            "Lines exceeding 79 characters:\n" + "\n".join(failures),
        )

    def test_comments_use_standard_pep8_prefix(self) -> None:
        """Require a space after ``#`` in explanatory comments."""

        failures: list[str] = []
        for path in python_paths():
            relative = path.relative_to(REPOSITORY_ROOT)
            source = path.read_bytes()
            for token in tokenize.tokenize(io.BytesIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                comment = token.string
                if token.start[0] == 1 and comment.startswith("#!"):
                    continue
                if comment == "#" or comment.startswith("# "):
                    continue
                failures.append(
                    f"{relative}:{token.start[0]}: {comment!r}"
                )
        self.assertEqual(
            [],
            failures,
            "Comments without a standard '# ' prefix:\n"
            + "\n".join(failures),
        )


if __name__ == "__main__":
    unittest.main()
