"""Physical composite dialogue records split into multiple editorial workbook rows.

Two canonical narration rows were previously treated as mapping anomalies because
their physical 27 28 records continue after the workbook's Japanese span.  In
both cases the continuation is intentional bytecode: page break, opcode 3D
(dynamic label), then an auxiliary text row.

The release compiler must treat each pair as one physical record and use
compile_anchored_record() so the 3D command remains exactly where intended.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompositeDialogueRecord:
    owner_id: str
    continuation_id: str
    bank: str
    resource: str
    marker_offset: int
    control: bytes

    def __post_init__(self) -> None:
        if not self.owner_id or not self.continuation_id:
            raise ValueError("composite dialogue IDs must not be empty")
        if self.marker_offset < 0:
            raise ValueError("composite marker offset must be non-negative")
        if len(self.control) != 3 or self.control[0] != 0x3D:
            raise ValueError("composite record control must be one opcode-3D command")


COMPOSITE_DIALOGUE_RECORDS = (
    CompositeDialogueRecord(
        owner_id="T00604",
        continuation_id="T00605",
        bank="MISSION_0",
        resource="KURUZER",
        marker_offset=0x00177DA8,
        control=bytes.fromhex("3D 00 06"),
    ),
    CompositeDialogueRecord(
        owner_id="T00893",
        continuation_id="T00894",
        bank="MISSION_1",
        resource="AK01",
        marker_offset=0x00CFA1C1,
        control=bytes.fromhex("3D 00 1B"),
    ),
)

BY_OWNER_ID = {item.owner_id: item for item in COMPOSITE_DIALOGUE_RECORDS}
CONTINUATION_IDS = frozenset(
    item.continuation_id for item in COMPOSITE_DIALOGUE_RECORDS
)


__all__ = [
    "BY_OWNER_ID",
    "COMPOSITE_DIALOGUE_RECORDS",
    "CONTINUATION_IDS",
    "CompositeDialogueRecord",
]
