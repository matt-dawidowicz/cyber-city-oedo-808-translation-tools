"""Regression tests for transactional image modification."""

from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock

from cyber_oedo.disc import patching
from cyber_oedo.disc.cdrom_mode1 import (
    MODE1_SYNC,
    PayloadPatch,
    rebuild_mode1_sector,
)
from cyber_oedo.disc.game_layout import MODE1_USER_DATA_OFFSET, RAW_SECTOR_SIZE


def _sector() -> bytes:
    """Construct a valid synthetic Mode 1 sector."""
    raw = bytearray(RAW_SECTOR_SIZE)
    raw[:12] = MODE1_SYNC
    raw[15] = 1
    raw[MODE1_USER_DATA_OFFSET:MODE1_USER_DATA_OFFSET + 3] = b"OLD"
    return rebuild_mode1_sector(raw)


class AtomicPatchingTests(unittest.TestCase):
    """Guarantee original images survive failed staged mutations."""

    def test_success_publishes_changes(self) -> None:
        """Replace the image after a successful guarded edit."""
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "image.img"
            image.write_bytes(_sector())
            patch = PayloadPatch(0, b"OLD", b"NEW", "synthetic")
            reports = patching.apply_payload_patches(
                image, (patch,), start_lba=0, sector_count=1
            )
            self.assertEqual(len(reports), 1)
            self.assertEqual(
                image.read_bytes()[MODE1_USER_DATA_OFFSET:MODE1_USER_DATA_OFFSET + 3],
                b"NEW",
            )
            self.assertEqual(sorted(p.name for p in image.parent.iterdir()), ["image.img"])

    def test_guard_failure_preserves_original(self) -> None:
        """Reject wrong source bytes without touching the image."""
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "image.img"
            original = _sector()
            image.write_bytes(original)
            patch = PayloadPatch(0, b"BAD", b"NEW", "synthetic")
            with self.assertRaisesRegex(ValueError, "source bytes differ"):
                patching.apply_payload_patches(
                    image, (patch,), start_lba=0, sector_count=1
                )
            self.assertEqual(image.read_bytes(), original)
            self.assertEqual(list(image.parent.iterdir()), [image])

    def test_publish_failure_preserves_original(self) -> None:
        """Do not publish partial bytes when atomic replacement fails."""
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "image.img"
            original = _sector()
            image.write_bytes(original)
            patch = PayloadPatch(0, b"OLD", b"NEW", "synthetic")
            with mock.patch.object(patching.os, "replace", side_effect=OSError("publish error")):
                with self.assertRaisesRegex(OSError, "publish error"):
                    patching.apply_payload_patches(
                        image, (patch,), start_lba=0, sector_count=1
                    )
            self.assertEqual(image.read_bytes(), original)
            self.assertEqual(list(image.parent.iterdir()), [image])


if __name__ == "__main__":
    unittest.main()
