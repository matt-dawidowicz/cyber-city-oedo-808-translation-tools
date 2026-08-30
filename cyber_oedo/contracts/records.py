"""Typed records for translator-owned durable file contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Mapping

from cyber_oedo.contracts.schemas import TRANSLATION_INVENTORY_V1


@dataclass(frozen=True, slots=True)
class TranslationInventoryRecord:
    """Represent one version-1 translator inventory occurrence row."""

    entry_id: str
    canonical_id: str
    occurrence_count: str
    kind: str
    bank: str
    quality: str
    offset: str
    sector: str
    source_bytes: str
    controls: str
    source_text: str
    tagged_source: str
    english_translation: str
    translator_notes: str

    @classmethod
    def from_mapping(
        cls,
        row: Mapping[str, object],
    ) -> TranslationInventoryRecord:
        """Build a typed row after requiring the version-1 schema fields."""

        TRANSLATION_INVENTORY_V1.require_compatible_header(tuple(row))
        values = {
            field: str(row[field])
            for field in TRANSLATION_INVENTORY_V1.fields
        }
        return cls(**values)

    def to_mapping(self) -> dict[str, str]:
        """Return the row using the canonical version-1 field names."""

        return asdict(self)
