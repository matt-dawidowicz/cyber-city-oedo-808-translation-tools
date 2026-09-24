from __future__ import annotations

import pathlib
import tempfile
import unittest

from cyber_oedo.runtime.text_renderer import (
    RENDERER_REGIONS,
    build_renderer_report,
    validate_renderer_regions,
)


class TextRendererProofTests(unittest.TestCase):
    def _write_synthetic_payload(self, root: pathlib.Path) -> pathlib.Path:
        end = max(
            region.payload_offset + len(region.expected)
            for region in RENDERER_REGIONS
        )
        data = bytearray(end + 1)
        for region in RENDERER_REGIONS:
            start = region.payload_offset
            data[start : start + len(region.expected)] = region.expected
        path = root / "track02.bin"
        path.write_bytes(data)
        return path

    def test_all_source_guards_match_synthetic_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            regions = validate_renderer_regions(path)
            self.assertTrue(all(item["matched"] for item in regions))
            self.assertEqual(
                {item["name"] for item in regions},
                {region.name for region in RENDERER_REGIONS},
            )

    def test_tampered_renderer_window_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            data = bytearray(path.read_bytes())
            target = RENDERER_REGIONS[2]
            data[target.payload_offset + 5] ^= 0x01
            path.write_bytes(data)

            regions = {
                item["name"]: item
                for item in validate_renderer_regions(path)
            }
            self.assertFalse(regions[target.name]["matched"])
            self.assertTrue(regions[RENDERER_REGIONS[0].name]["matched"])

    def test_synthetic_source_guard_does_not_claim_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            report = build_renderer_report(path)
            self.assertTrue(report["all_source_guards_match"])
            self.assertFalse(report["payload_authenticated"])


if __name__ == "__main__":
    unittest.main()
