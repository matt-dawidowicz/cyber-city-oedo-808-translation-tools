"""Model runtime-engine facts that cross the Tier A/Tier B boundary."""

from cyber_oedo.runtime.dialogue_interpreter import (
    DIALOGUE_INTERPRETER_CPU,
    MISSION0_MODULE_PAYLOAD_BASE,
    RUNTIME_REGIONS,
    cpu_to_payload,
    indexed_record_address,
    indexed_text_field_offset,
    validate_runtime_regions,
)

__all__ = [
    "DIALOGUE_INTERPRETER_CPU",
    "MISSION0_MODULE_PAYLOAD_BASE",
    "RUNTIME_REGIONS",
    "cpu_to_payload",
    "indexed_record_address",
    "indexed_text_field_offset",
    "validate_runtime_regions",
]
