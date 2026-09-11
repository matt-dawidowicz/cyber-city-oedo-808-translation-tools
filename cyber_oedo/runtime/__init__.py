"""Model runtime-engine facts that cross the Tier A/Tier B boundary."""

from cyber_oedo.runtime.dialogue_interpreter import (
    DIALOGUE_INTERPRETER_CPU,
    INDEXED_TABLE_ABSOLUTE_LBA,
    MISSION0_MODULE_PAYLOAD_BASE,
    RUNTIME_REGIONS,
    absolute_lba_to_payload_offset,
    cpu_to_payload,
    indexed_record_address,
    indexed_table_evidence,
    indexed_table_source_offset,
    indexed_text_field_offset,
    validate_runtime_regions,
)
from cyber_oedo.runtime.ram_probe import (
    B3_RAM_CANDIDATES,
    CD_RAM_BANKS,
    LIVE_H_BARTEN_BANKS,
    SYSTEM_CARD_3_RAM_BANKS,
    MprMapping,
    MprSnapshot,
    candidate_mappings,
    summarize_candidate_usage,
)

__all__ = [
    "B3_RAM_CANDIDATES",
    "CD_RAM_BANKS",
    "DIALOGUE_INTERPRETER_CPU",
    "INDEXED_TABLE_ABSOLUTE_LBA",
    "LIVE_H_BARTEN_BANKS",
    "MISSION0_MODULE_PAYLOAD_BASE",
    "MprMapping",
    "MprSnapshot",
    "RUNTIME_REGIONS",
    "SYSTEM_CARD_3_RAM_BANKS",
    "absolute_lba_to_payload_offset",
    "candidate_mappings",
    "cpu_to_payload",
    "indexed_record_address",
    "indexed_table_evidence",
    "indexed_table_source_offset",
    "indexed_text_field_offset",
    "summarize_candidate_usage",
    "validate_runtime_regions",
]
