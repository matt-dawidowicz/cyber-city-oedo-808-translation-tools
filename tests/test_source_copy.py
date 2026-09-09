"""Regression tests for copy-time source authentication."""

from __future__ import annotations

import hashlib
import pathlib
import tempfile
import unittest

from cyber_oedo.build.source import copy_authenticated_source_set


class AuthenticatedCopyTests(unittest.TestCase):
    """Verify authentication is folded into copying without weakening guards."""

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
                self.assertEqual(output_paths[extension].read_bytes(), payload)

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


if __name__ == "__main__":
    unittest.main()
