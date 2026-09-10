"""Regression tests for versioned machine-readable toolkit contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cyber_oedo.commands.plan_human_test import build_payload
from cyber_oedo.contracts import (
    BUILD_PLAN_V1,
    TRANSLATION_INVENTORY_V1,
    TranslationInventoryRecord,
    contracts_document,
)


class ContractTests(unittest.TestCase):
    """Keep schema versions explicit, deterministic, and compatible."""

    def test_catalog_has_stable_versioned_identifiers(self) -> None:
        """Expose every descriptor with an explicit positive version."""

        document = contracts_document()
        self.assertEqual(document["catalog_version"], 1)
        for item in document["contracts"]:
            self.assertGreater(item["version"], 0)
            self.assertIn("/v", item["identifier"])

    def test_inventory_fields_are_owned_by_contract(self) -> None:
        """Use the contract descriptor as the inventory facade schema."""

        from cyber_oedo.text import build_translation_inventory

        self.assertEqual(
            build_translation_inventory.OUTPUT_FIELDS,
            TRANSLATION_INVENTORY_V1.fields,
        )

    def test_typed_inventory_record_round_trips(self) -> None:
        """Preserve every translator inventory field through typed mapping."""

        row = {
            field: f"value-{index}"
            for index, field in enumerate(TRANSLATION_INVENTORY_V1.fields)
        }
        record = TranslationInventoryRecord.from_mapping(row)
        self.assertEqual(record.to_mapping(), row)

    def test_missing_inventory_field_is_rejected(self) -> None:
        """Reject incompatible headers before row processing begins."""

        fields = TRANSLATION_INVENTORY_V1.fields[:-1]
        with self.assertRaises(ValueError):
            TRANSLATION_INVENTORY_V1.require_compatible_header(fields)

    def test_dry_run_plan_is_versioned_and_deterministic(self) -> None:
        """Emit stable plan metadata without embedding source bytes."""

        first = build_payload("original")
        second = build_payload("original")
        self.assertEqual(first, second)
        self.assertEqual(first["contract"], BUILD_PLAN_V1.identifier)
        self.assertEqual(first["schema_version"], 1)
        serialized = str(first)
        self.assertNotIn("expected_hex", serialized)
        self.assertNotIn("replacement_hex", serialized)

    def test_inventory_summary_accepts_header_only_file(self) -> None:
        """Return zero counts for a valid empty translator inventory."""

        from cyber_oedo.commands.inventory_summary import summarize

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inventory.tsv"
            path.write_text(
                "\t".join(TRANSLATION_INVENTORY_V1.fields) + "\n",
                encoding="utf-8",
            )
            summary = summarize(path)
        self.assertEqual(summary["rows"], 0)
        self.assertEqual(summary["translated_rows"], 0)


if __name__ == "__main__":
    unittest.main()
