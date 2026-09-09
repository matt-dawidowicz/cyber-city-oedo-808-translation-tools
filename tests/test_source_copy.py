"""Regression tests for copy-time source authentication."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest
from unittest import mock

from cyber_oedo.build import source as source_module
from cyber_oedo.build.source import copy_authenticated_source_set


class AuthenticatedCopyTests(unittest.TestCase):
    """Verify copy-time authentication without weakening source guards."""

    def _source_set(
        self,
        root: pathlib.Path,
    ) -> tuple[pathlib.Path, dict[str, str], dict[str, bytes]]:
        """Create a tiny synthetic CloneCD triplet and expected hashes."""

        data = {
            ".ccd": b"descriptor\n",
            ".img": bytes(range(256)) * 64,
            ".sub": b"subchannel" * 32,
        }
        ccd = root / "game.ccd"
        hashes: dict[str, str] = {}
        for extension, payload in data.items():
            path = ccd.with_suffix(extension)
            path.write_bytes(payload)
            hashes[extension] = hashlib.sha256(payload).hexdigest()
        return ccd, hashes, data

    def test_copy_authenticates_and_preserves_bytes(self) -> None:
        """Hash source bytes during copy and reproduce the exact triplet."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source_dir = root / "source"
            source_dir.mkdir()
            ccd, hashes, data = self._source_set(source_dir)
            destination = root / "output"
            source_paths, output_paths = copy_authenticated_source_set(
                ccd,
                destination,
                "copy",
                hashes,
                chunk_size=17,
            )
            self.assertEqual(source_paths[".ccd"], ccd.resolve())
            for extension, payload in data.items():
                self.assertEqual(
                    output_paths[extension].read_bytes(),
                    payload,
                )

    def test_hash_failure_removes_created_copies(self) -> None:
        """Do not leave a partial copied set after authentication failure."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source_dir = root / "source"
            source_dir.mkdir()
            ccd, hashes, _ = self._source_set(source_dir)
            hashes[".img"] = "0" * 64
            destination = root / "output"
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                copy_authenticated_source_set(
                    ccd,
                    destination,
                    "copy",
                    hashes,
                    chunk_size=13,
                )
            self.assertEqual(list(destination.iterdir()), [])

    def test_copy_exception_removes_partial_destination(self) -> None:
        """Remove a file even when copying itself raises before hashing."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source_dir = root / "source"
            source_dir.mkdir()
            ccd, hashes, _ = self._source_set(source_dir)
            destination = root / "output"

            def failing_copy(
                source: pathlib.Path,
                output: pathlib.Path,
                *,
                chunk_size: int,
            ) -> str:
                """Create partial output, then emulate an I/O failure."""

                del source, chunk_size
                output.write_bytes(b"partial")
                raise OSError("synthetic copy failure")

            with mock.patch.object(
                source_module,
                "_copy_and_hash",
                side_effect=failing_copy,
            ):
                with self.assertRaisesRegex(
                    OSError,
                    "synthetic copy failure",
                ):
                    copy_authenticated_source_set(
                        ccd,
                        destination,
                        "copy",
                        hashes,
                    )
            self.assertEqual(list(destination.iterdir()), [])

    def test_existing_output_is_never_overwritten_or_deleted(self) -> None:
        """Reject a destination collision before opening any output file."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source_dir = root / "source"
            source_dir.mkdir()
            ccd, hashes, _ = self._source_set(source_dir)
            destination = root / "output"
            destination.mkdir()
            existing = destination / "copy.ccd"
            existing.write_bytes(b"keep me")
            with self.assertRaisesRegex(FileExistsError, "overwrite"):
                copy_authenticated_source_set(
                    ccd,
                    destination,
                    "copy",
                    hashes,
                )
            self.assertEqual(existing.read_bytes(), b"keep me")
            self.assertEqual(
                sorted(path.name for path in destination.iterdir()),
                ["copy.ccd"],
            )


if __name__ == "__main__":
    unittest.main()
