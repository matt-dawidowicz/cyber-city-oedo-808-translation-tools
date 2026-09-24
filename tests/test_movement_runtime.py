from __future__ import annotations

import pathlib
import tempfile
import unittest

from cyber_oedo.runtime.movement import (
    IDLE_ANIMATION_SCRIPTS,
    INPUT_CODES,
    INTERACTION_BOUNDS_BYTES,
    INTERACTION_PAYLOAD_BYTES,
    INTERACTION_RECORD_BYTES,
    MOVEMENT_REGIONS,
    TILE_VECTORS,
    UNIT_VECTORS,
    WALK_ANIMATION_SCRIPTS,
    build_movement_report,
    validate_movement_regions,
)


class MovementProofTests(unittest.TestCase):
    def _write_synthetic_payload(self, root: pathlib.Path) -> pathlib.Path:
        end = max(
            region.payload_offset + len(region.expected)
            for region in MOVEMENT_REGIONS
        )
        data = bytearray(end + 1)
        for region in MOVEMENT_REGIONS:
            start = region.payload_offset
            data[start : start + len(region.expected)] = region.expected
        path = root / "track02.bin"
        path.write_bytes(data)
        return path

    def test_direction_tables_match_input_normalization(self) -> None:
        self.assertEqual(INPUT_CODES[1], "left")
        self.assertEqual(INPUT_CODES[2], "down")
        self.assertEqual(INPUT_CODES[3], "right")
        self.assertEqual(INPUT_CODES[4], "up")
        self.assertEqual(UNIT_VECTORS[1], (-1, 0))
        self.assertEqual(UNIT_VECTORS[4], (0, -1))
        self.assertEqual(TILE_VECTORS[1], (-16, 0))
        self.assertEqual(TILE_VECTORS[3], (16, 0))


    def test_animation_script_selection_matches_direction_codes(self) -> None:
        self.assertEqual(WALK_ANIMATION_SCRIPTS, {
            1: 0x4649,
            2: 0x4654,
            3: 0x465F,
            4: 0x466A,
        })
        self.assertEqual(IDLE_ANIMATION_SCRIPTS, {
            1: 0x4675,
            2: 0x467A,
            3: 0x467F,
            4: 0x4684,
        })

    def test_interaction_record_layout_is_18_bytes(self) -> None:
        self.assertEqual(INTERACTION_RECORD_BYTES, 18)
        self.assertEqual(
            1 + INTERACTION_BOUNDS_BYTES + INTERACTION_PAYLOAD_BYTES,
            INTERACTION_RECORD_BYTES,
        )

    def test_report_exposes_collision_and_interaction_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            report = build_movement_report(path)
            self.assertEqual(report["collision"]["tile_size_pixels"], 16)
            self.assertEqual(report["collision"]["storage"], "one bit per map tile")
            self.assertEqual(report["interaction_records"]["record_bytes"], 18)
            self.assertEqual(report["interaction_records"]["payload_bytes"], 9)
            self.assertEqual(
                report["state"]["animation_script_pointer"],
                "$2765/$2766",
            )

    def test_all_source_guards_match_synthetic_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            regions = validate_movement_regions(path)
            self.assertTrue(all(item["matched"] for item in regions))

    def test_tampered_movement_window_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            data = bytearray(path.read_bytes())
            target = MOVEMENT_REGIONS[-1]
            data[target.payload_offset + 2] ^= 0x01
            path.write_bytes(data)
            regions = {
                item["name"]: item
                for item in validate_movement_regions(path)
            }
            self.assertFalse(regions[target.name]["matched"])

    def test_synthetic_payload_does_not_claim_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_synthetic_payload(pathlib.Path(directory))
            report = build_movement_report(path)
            self.assertTrue(report["all_source_guards_match"])
            self.assertFalse(report["payload_authenticated"])


if __name__ == "__main__":
    unittest.main()
