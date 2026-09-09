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

__all__ = [
    "DIALOGUE_INTERPRETER_CPU",
    "INDEXED_TABLE_ABSOLUTE_LBA",
    "MISSION0_MODULE_PAYLOAD_BASE",
    "RUNTIME_REGIONS",
    "absolute_lba_to_payload_offset",
    "cpu_to_payload",
    "indexed_record_address",
    "indexed_table_evidence",
    "indexed_table_source_offset",
    "indexed_text_field_offset",
    "validate_runtime_regions",
]
