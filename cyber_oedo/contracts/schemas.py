"""Define explicit versions for stable CLI file and JSON contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Sequence


@dataclass(frozen=True, slots=True)
class ContractDescriptor:
    """Describe one versioned external data contract.

    Args:
        name: Stable machine-readable contract name.
        version: Positive integer schema version.
        kind: Serialization family such as ``tsv`` or ``json``.
        fields: Ordered tabular fields or stable top-level JSON keys.
        editable_fields: Fields intentionally owned by human editors.
    """

    name: str
    version: int
    kind: str
    fields: tuple[str, ...]
    editable_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject malformed descriptors before they become public metadata."""

        if not self.name or self.version <= 0:
            raise ValueError("contract name and positive version are required")
        if self.kind not in {"tsv", "json"}:
            raise ValueError("contract kind must be tsv or json")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("contract fields must be unique")
        if not set(self.editable_fields).issubset(self.fields):
            raise ValueError("editable fields must belong to the contract")

    @property
    def identifier(self) -> str:
        """Return the stable contract identifier including its version."""

        return f"cyber-oedo.{self.name}/v{self.version}"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe contract description."""

        payload = asdict(self)
        payload["identifier"] = self.identifier
        return payload

    def require_compatible_header(self, actual: Sequence[str]) -> None:
        """Require every field in this contract to exist in a TSV header.

        Args:
            actual: Header fields found in an input file.

        Raises:
            ValueError: If one or more required fields are missing.

        Notes:
            Extra columns are accepted so additive informational fields remain
            forward-compatible with readers of the same major schema.
        """

        missing = [field for field in self.fields if field not in actual]
        if missing:
            raise ValueError(
                "missing required fields: " + ", ".join(missing)
            )


DIALOGUE_V1 = ContractDescriptor(
    name="dialogue-tsv",
    version=1,
    kind="tsv",
    fields=(
        "bank",
        "quality",
        "offset",
        "sector",
        "within_sector",
        "record_bytes",
        "sjis_characters",
        "controls",
        "tagged_text",
        "text",
        "raw_hex",
    ),
)

AUXILIARY_TEXT_V1 = ContractDescriptor(
    name="auxiliary-text-tsv",
    version=1,
    kind="tsv",
    fields=(
        "bank",
        "offset",
        "sector",
        "within_sector",
        "bytes",
        "characters",
        "text",
    ),
)

TRANSLATION_INVENTORY_V1 = ContractDescriptor(
    name="translation-inventory-tsv",
    version=1,
    kind="tsv",
    fields=(
        "entry_id",
        "canonical_id",
        "occurrence_count",
        "kind",
        "bank",
        "quality",
        "offset",
        "sector",
        "source_bytes",
        "controls",
        "source_text",
        "tagged_source",
        "english_translation",
        "translator_notes",
    ),
    editable_fields=(
        "english_translation",
        "translator_notes",
    ),
)

BUILD_PLAN_V1 = ContractDescriptor(
    name="human-test-build-plan-json",
    version=1,
    kind="json",
    fields=(
        "contract",
        "schema_version",
        "plan_sha256",
        "profile",
        "plan",
    ),
)

BUILD_MANIFEST_V1 = ContractDescriptor(
    name="human-test-build-manifest-json",
    version=1,
    kind="json",
    fields=(
        "build_profile",
        "title_screen_mode",
        "created_utc",
        "scope",
        "source_hashes",
        "output_hashes",
        "image_bytes",
        "changed_absolute_lbas",
        "changed_relative_sectors",
        "guarded_relative_sectors",
        "modified_sectors",
        "text_patches",
        "binary_patches",
        "verification",
    ),
)

INVENTORY_SUMMARY_V1 = ContractDescriptor(
    name="translation-inventory-summary-json",
    version=1,
    kind="json",
    fields=(
        "contract",
        "schema_version",
        "source_schema",
        "rows",
        "canonical_ids",
        "translated_rows",
        "blank_translation_rows",
        "quality_counts",
    ),
)

ALL_CONTRACTS = (
    DIALOGUE_V1,
    AUXILIARY_TEXT_V1,
    TRANSLATION_INVENTORY_V1,
    BUILD_PLAN_V1,
    BUILD_MANIFEST_V1,
    INVENTORY_SUMMARY_V1,
)


def contracts_document() -> dict[str, object]:
    """Return the complete machine-readable external contract catalog."""

    return {
        "catalog_version": 1,
        "contracts": [item.to_dict() for item in ALL_CONTRACTS],
    }
