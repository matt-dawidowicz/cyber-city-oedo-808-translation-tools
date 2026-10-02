"""Insertion planning for the finalized common-dialogue localization.

The editorial workbook is exported to TSV before build use. This module maps
each row back to the authenticated payload, checks packed-English capacity,
and emits guarded in-place patches only when every gate passes. Rows that
need growth are reported for relocation; they are never truncated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.packed_english_runtime import (
    IGNORED_FIELD_PADDING,
    encode_fixed_footprint,
)
from cyber_oedo.text.layout import DIALOGUE_MARKER
from cyber_oedo.text.packed_english import PackedEnglishDictionary, PackedEnglishError

FINAL_DIALOGUE_MASTER_SHA256 = "44ea963798e953a289e6614820579b6484dc7183af43ba031ecef105c27fb502"
FINAL_LOCALIZATION_WORKBOOK_SHA256 = "6701f387ff62ac365aab9d902945ec0d90661c7e91e4baa713fa120cd2d8c95a"
DIALOGUE_CATEGORIES = frozenset({"Spoken dialogue", "Narration / description"})

class FinalDialogueInsertionError(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class FinalDialogueRow:
    entry_id: str
    bank: str
    category: str
    resource: str
    offset: int
    japanese_source: str
    english: str
    quality: str = ""
    occurrences: str = ""
    display_strategy: str = ""

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise FinalDialogueInsertionError("dialogue row is missing its ID")
        if self.category not in DIALOGUE_CATEGORIES:
            raise FinalDialogueInsertionError(f"{self.entry_id}: unsupported category")
        if self.offset < 0 or not self.japanese_source or not self.english:
            raise FinalDialogueInsertionError(f"{self.entry_id}: incomplete row")

    @property
    def visible_offset(self) -> int:
        return self.offset + len(DIALOGUE_MARKER)

    @property
    def source_bytes(self) -> bytes:
        try:
            return self.japanese_source.encode("shift_jis")
        except UnicodeEncodeError as error:
            raise FinalDialogueInsertionError(
                f"{self.entry_id}: Japanese source is not strict Shift-JIS"
            ) from error

@dataclass(frozen=True, slots=True)
class DialogueInsertionAudit:
    row: FinalDialogueRow
    marker_matches: bool
    source_matches: bool
    source_bytes: int
    packed_bytes: int | None
    status: str
    detail: str

    @property
    def can_patch_exactly(self) -> bool:
        return self.status == "exact_footprint"

    @property
    def is_padding_candidate(self) -> bool:
        return self.status == "padding_candidate"

    @property
    def can_patch_in_place(self) -> bool:
        return self.status in {"exact_footprint", "padding_candidate"}

    @property
    def needs_relocation(self) -> bool:
        return self.status == "relocation_required"

def load_final_dialogue_tsv(path: Path) -> tuple[FinalDialogueRow, ...]:
    required = ("ID", "Bank", "Category", "Resource", "Offset", "Japanese Source", "Final Localization")
    rows: list[FinalDialogueRow] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fieldnames = tuple(reader.fieldnames or ())
        missing = [name for name in required if name not in fieldnames]
        if missing:
            raise FinalDialogueInsertionError("missing TSV columns: " + ", ".join(missing))
        seen: set[str] = set()
        for raw in reader:
            if raw["Category"] not in DIALOGUE_CATEGORIES:
                continue
            entry_id = (raw["ID"] or "").strip()
            if entry_id in seen:
                raise FinalDialogueInsertionError(f"duplicate final-dialogue ID: {entry_id}")
            seen.add(entry_id)
            try:
                offset = int((raw["Offset"] or "").strip(), 16)
            except ValueError as error:
                raise FinalDialogueInsertionError(f"{entry_id}: bad offset") from error
            rows.append(FinalDialogueRow(
                entry_id=entry_id,
                bank=(raw["Bank"] or "").strip(),
                category=(raw["Category"] or "").strip(),
                resource=(raw["Resource"] or "").strip(),
                offset=offset,
                japanese_source=raw["Japanese Source"] or "",
                english=raw["Final Localization"] or "",
                quality=(raw.get("Quality") or "").strip(),
                occurrences=(raw.get("Occurrences") or "").strip(),
                display_strategy=(raw.get("Display Strategy") or "").strip(),
            ))
    return tuple(rows)

def audit_row(payload: bytes, row: FinalDialogueRow, dictionary: PackedEnglishDictionary) -> DialogueInsertionAudit:
    marker = payload[row.offset:row.offset + len(DIALOGUE_MARKER)]
    marker_matches = marker == DIALOGUE_MARKER
    source = row.source_bytes
    actual = payload[row.visible_offset:row.visible_offset + len(source)]
    source_matches = actual == source
    if not marker_matches:
        return DialogueInsertionAudit(row, False, False, len(source), None, "mapping_required", "dialogue marker absent at workbook offset")
    if not source_matches:
        return DialogueInsertionAudit(row, True, False, len(source), None, "mapping_required", "Japanese span does not match authenticated bytes")
    try:
        packed = dictionary.encode_visible_text(row.english)
    except PackedEnglishError as error:
        return DialogueInsertionAudit(row, True, True, len(source), None, "encoding_required", str(error))
    if len(packed) > len(source):
        return DialogueInsertionAudit(row, True, True, len(source), len(packed), "relocation_required", f"packed English needs {len(packed)} bytes; source span owns {len(source)}")
    if len(packed) == len(source):
        return DialogueInsertionAudit(
            row, True, True, len(source), len(packed), "exact_footprint",
            "packed English exactly fills the authenticated visible span",
        )
    return DialogueInsertionAudit(
        row, True, True, len(source), len(packed), "padding_candidate",
        f"fits only if stock-ignored ${IGNORED_FIELD_PADDING:02X} padding is live-certified",
    )

def audit_rows(payload: bytes, rows: Iterable[FinalDialogueRow], dictionary: PackedEnglishDictionary) -> tuple[DialogueInsertionAudit, ...]:
    return tuple(audit_row(payload, row, dictionary) for row in rows)

def build_in_place_patches(
    payload: bytes,
    rows: Iterable[FinalDialogueRow],
    dictionary: PackedEnglishDictionary,
    *,
    allowed_banks: frozenset[str] | None = None,
    allow_padding_candidates: bool = False,
) -> tuple[PayloadPatch, ...]:
    patches: list[PayloadPatch] = []
    for row in rows:
        if allowed_banks is not None and row.bank not in allowed_banks:
            continue
        audit = audit_row(payload, row, dictionary)
        if not audit.can_patch_exactly and not (
            allow_padding_candidates and audit.is_padding_candidate
        ):
            continue
        source = row.source_bytes
        replacement = encode_fixed_footprint(dictionary, row.english, len(source))
        patches.append(PayloadPatch(
            offset=row.visible_offset,
            expected=source,
            replacement=replacement,
            label=f"{row.entry_id} {row.bank} final packed-English dialogue",
        ))
    return tuple(patches)

def summarize_audit(audits: Iterable[DialogueInsertionAudit]) -> dict[str, int]:
    counts = {
        "total": 0,
        "exact_footprint": 0,
        "padding_candidate": 0,
        "relocation_required": 0,
        "mapping_required": 0,
        "encoding_required": 0,
    }
    for audit in audits:
        counts["total"] += 1
        counts[audit.status] += 1
    return counts
