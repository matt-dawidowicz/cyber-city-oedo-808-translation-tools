"""Versioned external contract descriptors and typed records."""

from cyber_oedo.contracts.records import TranslationInventoryRecord
from cyber_oedo.contracts.schemas import (
    ALL_CONTRACTS,
    AUXILIARY_TEXT_V1,
    BUILD_MANIFEST_V1,
    BUILD_PLAN_V1,
    DIALOGUE_V1,
    INVENTORY_SUMMARY_V1,
    TRANSLATION_INVENTORY_V1,
    ContractDescriptor,
    contracts_document,
)

__all__ = [
    "ALL_CONTRACTS",
    "AUXILIARY_TEXT_V1",
    "BUILD_MANIFEST_V1",
    "BUILD_PLAN_V1",
    "DIALOGUE_V1",
    "INVENTORY_SUMMARY_V1",
    "TRANSLATION_INVENTORY_V1",
    "ContractDescriptor",
    "TranslationInventoryRecord",
    "contracts_document",
]
