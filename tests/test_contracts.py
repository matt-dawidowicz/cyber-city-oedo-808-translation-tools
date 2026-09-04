"""Regression tests for the restart baseline's external contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cyber_oedo.contracts import (
    TRANSLATION_INVENTORY_V1,
    TranslationInventoryRecord,
    contracts_document,
)


class ContractTests(unittest.TestCase):
    """Keep the reduced contract catalog explicit and deterministic."""

    def test_catalog_contains_only_restart_contracts(self) -> None:
        """Exclude abandoned human-test build contracts."""

        document = contracts_document()
        identifiers = {
            item["identifier"] for item in document["contracts"]
        }
        self.assertEqual(document["catalog_version"], 1)
        self.assertEqual(len(identifiers), 4)
        self.assertFalse(any("human-test" in item for item in identifiers))

    def test_inventory_fields_are_owned_by_contract(self) -> None:
        """Use the contract descriptor as the inventory schema."""

        from cyber_oedo.text import build_translation_inventory

        self.assertEqual(
            build_translation_inventory.OUTPUT_FIELDS,
            TRANSLATION_INVENTORY_V1.fields,
        )

    def test_typed_inventory_record_round_trips(self) -> None:
        """Preserve translator inventory fields through typed mapping."""

        row = {
            field: f"value-{index}"
            for index, field in enumerate(TRANSLATION_INVENTORY_V1.fields)
        }
        record = TranslationInventoryRecord.from_mapping(row)
        self.assertEqual(record.to_mapping(), row)

    def test_missing_inventory_field_is_rejected(self) -> None:
        """Reject incompatible headers before row processing."""

        with self.assertRaises(ValueError):
            TRANSLATION_INVENTORY_V1.require_compatible_header(
                TRANSLATION_INVENTORY_V1.fields[:-1]
            )

    def test_inventory_summary_accepts_header_only_file(self) -> None:
        """Return zero counts for a valid empty inventory."""

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
