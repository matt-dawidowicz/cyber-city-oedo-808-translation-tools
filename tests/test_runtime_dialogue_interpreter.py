"""Test the first source-guarded Tier-B runtime proof model."""

from __future__ import annotations

import csv
import pathlib
import tempfile
import unittest

from cyber_oedo.runtime.dialogue_interpreter import (
    HISTORICAL_ZERO_REGION_CPU,
    INDEXED_ALTERNATE_TEXT_OFFSET,
    MISSION0_MODULE_PAYLOAD_BASE,
    RUNTIME_REGIONS,
    _three_d_patterns,
    cpu_to_payload,
    indexed_record_address,
    indexed_text_field_offset,
    validate_runtime_regions,
)


class RuntimeDialogueInterpreterTests(unittest.TestCase):
    """Keep Tier-B static claims exact and source-guarded."""

    def test_cpu_to_payload_matches_mission0_mapping(self) -> None:
        """Translate the known dialogue entry to its Track 2 coordinate."""

        self.assertEqual(cpu_to_payload(0x9543), 0x0013AD43)
        self.assertEqual(
            cpu_to_payload(HISTORICAL_ZERO_REGION_CPU),
            0x0013B71B,
        )

    def test_cpu_to_payload_rejects_unmapped_addresses(self) -> None:
        """Reject addresses outside the known module mapping."""

        with self.assertRaises(ValueError):
            cpu_to_payload(0xA000)
        with self.assertRaises(TypeError):
            cpu_to_payload(True)

    def test_indexed_record_address_matches_6694_math(self) -> None:
        """Model the one-based 32-byte record table calculation."""

        cases = {
            0x01: 0xA400,
            0x06: 0xA4A0,
            0x18: 0xA6E0,
            0x22: 0xA820,
            0x00: 0xC3E0,
        }
        for index, expected in cases.items():
            with self.subTest(index=index):
                self.assertEqual(indexed_record_address(index), expected)

    def test_indexed_field_selection_matches_3d_handler(self) -> None:
        """Use the alternate field only when record byte 1A is zero."""

        self.assertEqual(indexed_text_field_offset(1), 0)
        self.assertEqual(indexed_text_field_offset(0xFF), 0)
        self.assertEqual(
            indexed_text_field_offset(0),
            INDEXED_ALTERNATE_TEXT_OFFSET,
        )

    def test_runtime_guards_accept_exact_synthetic_source(self) -> None:
        """Accept a synthetic image containing every exact guard."""

        size = MISSION0_MODULE_PAYLOAD_BASE + 0xA000
        payload = bytearray(size)
        for region in RUNTIME_REGIONS:
            offset = region.payload_offset
            payload[offset:offset + len(region.expected)] = region.expected
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "payload.bin"
            path.write_bytes(payload)
            results = validate_runtime_regions(path)
        self.assertTrue(all(item["matched"] for item in results))
        zero_region = next(
            item for item in results
            if item["name"] == "historical_zero_region"
        )
        self.assertFalse(zero_region["ownership_proven"])

    def test_runtime_guards_reject_one_changed_byte(self) -> None:
        """Detect source drift before any Tier-B patch design is used."""

        size = MISSION0_MODULE_PAYLOAD_BASE + 0xA000
        payload = bytearray(size)
        for region in RUNTIME_REGIONS:
            offset = region.payload_offset
            payload[offset:offset + len(region.expected)] = region.expected
        first = RUNTIME_REGIONS[0]
        payload[first.payload_offset] ^= 0xFF
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "payload.bin"
            path.write_bytes(payload)
            results = validate_runtime_regions(path)
        matched = {item["name"]: item["matched"] for item in results}
        self.assertFalse(matched[first.name])

    def test_three_d_tsv_summary_keeps_operand_pairs(
        self,
    ) -> None:
        """Correlate Tier-A 3D evidence without changing other controls."""

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "dialogue.tsv"
            with path.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(
                    output,
                    fieldnames=("controls",),
                    delimiter="\t",
                )
                writer.writeheader()
                writer.writerow({"controls": "3D 00 06"})
                writer.writerow({"controls": "40 3D 00 18 21"})
                writer.writerow({"controls": ""})
            report = _three_d_patterns(path)
        self.assertEqual(report["rows_with_3d"], 2)
        self.assertEqual(report["occurrences"], 2)
        self.assertEqual(
            [(row["arg0"], row["arg1"]) for row in report["patterns"]],
            [("0x00", "0x06"), ("0x00", "0x18")],
        )


if __name__ == "__main__":
    unittest.main()
