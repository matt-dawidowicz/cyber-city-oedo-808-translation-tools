"""Compile the Definitive Edition dialogue master against authenticated records."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from cyber_oedo.script import ControlCommand, TextRun, parse_dialogue_record
from cyber_oedo.script.opcodes import DialogueOpcode
from cyber_oedo.text.composite_dialogue_records import BY_OWNER_ID, CONTINUATION_IDS
from cyber_oedo.text.definitive_control_anchors import DEFINITIVE_CONTROL_ANCHORS
from cyber_oedo.text.english_dialogue_engine import (
    EnglishDialogueCompileError,
    EnglishGlyphTable,
    compile_anchored_record,
    compile_automatic_record,
)

DEFINITIVE_WORKBOOK_SHA256 = (
    "f4a0d84fa903e911b5075154282cd5323c025330542e082e7d470e21105f0c5b"
)
DEFINITIVE_SCRIPT_TSV_SHA256 = (
    "b59efc5e4953cc7a4683f2d8e11fbb0135f436d4a1a327915d1b2bd298d2bc7b"
)
DEFINITIVE_DIALOGUE_TSV_SHA256 = (
    "334f4a61bc167c95f6d7ec6ad51813c8929f759e38faa133d4097b8f7dffa303"
)


@dataclass(frozen=True, slots=True)
class DefinitiveScriptRow:
    entry_id: str
    bank: str
    category: str
    resource: str
    offset: int
    japanese_source: str
    english: str
    voice: str = ""
    quality: str = ""
    occurrences: str = ""
    status: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CompiledDialogueRow:
    row: DefinitiveScriptRow
    source_record: bytes | None
    compiled_record: bytes | None
    status: str
    detail: str
    mid_controls: tuple[int, ...] = ()

    @property
    def size_delta(self) -> int | None:
        if self.source_record is None or self.compiled_record is None:
            return None
        return len(self.compiled_record) - len(self.source_record)


def load_definitive_script_tsv(path: Path) -> tuple[DefinitiveScriptRow, ...]:
    required = (
        "ID",
        "Bank",
        "Category",
        "Resource",
        "Offset",
        "Japanese Source",
        "Definitive Localization",
    )
    result: list[DefinitiveScriptRow] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        names = tuple(reader.fieldnames or ())
        missing = [name for name in required if name not in names]
        if missing:
            raise ValueError("definitive TSV missing columns: " + ", ".join(missing))
        for raw in reader:
            try:
                offset = int((raw["Offset"] or "").strip(), 16)
            except ValueError as error:
                raise ValueError(f"{raw.get('ID')}: invalid offset") from error
            result.append(
                DefinitiveScriptRow(
                    entry_id=(raw["ID"] or "").strip(),
                    bank=(raw["Bank"] or "").strip(),
                    category=(raw["Category"] or "").strip(),
                    resource=(raw["Resource"] or "").strip(),
                    offset=offset,
                    japanese_source=raw["Japanese Source"] or "",
                    english=raw["Definitive Localization"] or "",
                    voice=(raw.get("Final Voice") or "").strip(),
                    quality=(raw.get("Quality") or "").strip(),
                    occurrences=(raw.get("Occurrences") or "").strip(),
                    status=(raw.get("Definitive Status") or "").strip(),
                    reason=(raw.get("Definitive Reason") or "").strip(),
                )
            )
    return tuple(result)


def _mid_controls(record) -> tuple[int, ...]:
    nodes = record.body.nodes
    text_indices = [index for index, node in enumerate(nodes) if isinstance(node, TextRun)]
    if not text_indices:
        return ()
    first = min(text_indices)
    last = max(text_indices)
    return tuple(
        node.opcode
        for index, node in enumerate(nodes)
        if isinstance(node, ControlCommand)
        and node.opcode != int(DialogueOpcode.PAGE_BREAK)
        and first < index < last
    )


def compile_direct_row(
    payload: bytes,
    row: DefinitiveScriptRow,
    glyphs: EnglishGlyphTable,
) -> CompiledDialogueRow:
    """Compile one row whose workbook offset is the physical record marker."""
    record = parse_dialogue_record(payload, row.offset)
    if record is None:
        return CompiledDialogueRow(
            row, None, None, "not_dialogue_record",
            "workbook offset is not a valid 27 28 dialogue record",
        )
    source = payload[row.offset : record.end_offset + 1]
    if record.body.visible_text != row.japanese_source:
        return CompiledDialogueRow(
            row,
            source,
            None,
            "split_or_mapped_record",
            "record visible text differs from this editorial row; compile at resource level",
            _mid_controls(record),
        )

    controls = _mid_controls(record)
    try:
        if not controls:
            compiled = compile_automatic_record(source, row.english, glyphs)
            mode = "automatic"
        else:
            fragments = DEFINITIVE_CONTROL_ANCHORS.get(row.entry_id)
            if fragments is None:
                return CompiledDialogueRow(
                    row,
                    source,
                    None,
                    "anchor_required",
                    "mid-text control has no frozen reviewed English fragment anchor",
                    controls,
                )
            compiled = compile_anchored_record(source, fragments, glyphs)
            mode = "anchored"
    except EnglishDialogueCompileError as error:
        return CompiledDialogueRow(
            row, source, None, "compile_error", str(error), controls
        )
    return CompiledDialogueRow(
        row,
        source,
        compiled,
        mode,
        "compiled against exact opcode-aware source record",
        controls,
    )


def _compile_composite_row(
    payload: bytes,
    owner: DefinitiveScriptRow,
    continuation: DefinitiveScriptRow,
    glyphs: EnglishGlyphTable,
) -> CompiledDialogueRow:
    spec = BY_OWNER_ID[owner.entry_id]
    if continuation.entry_id != spec.continuation_id:
        return CompiledDialogueRow(
            owner, None, None, "composite_mapping_error",
            f"expected continuation {spec.continuation_id}, found {continuation.entry_id}",
        )
    if owner.bank != spec.bank or owner.resource != spec.resource:
        return CompiledDialogueRow(
            owner, None, None, "composite_mapping_error",
            "composite owner bank/resource differs from reviewed ownership map",
        )
    record = parse_dialogue_record(payload, spec.marker_offset)
    if record is None:
        return CompiledDialogueRow(
            owner, None, None, "not_dialogue_record",
            "composite marker is not a valid 27 28 dialogue record",
        )
    source = payload[spec.marker_offset : record.end_offset + 1]
    expected_visible = owner.japanese_source + continuation.japanese_source
    if record.body.visible_text != expected_visible:
        return CompiledDialogueRow(
            owner, source, None, "composite_source_mismatch",
            "physical composite visible text differs from owner + continuation rows",
            _mid_controls(record),
        )
    mid_commands = tuple(
        node
        for node in record.body.nodes
        if isinstance(node, ControlCommand)
        and node.opcode != int(DialogueOpcode.PAGE_BREAK)
    )
    if len(mid_commands) != 1 or mid_commands[0].raw != spec.control:
        return CompiledDialogueRow(
            owner, source, None, "composite_control_mismatch",
            "physical composite control differs from reviewed opcode-3D command",
            _mid_controls(record),
        )
    fragments = DEFINITIVE_CONTROL_ANCHORS.get(owner.entry_id)
    if fragments is None:
        return CompiledDialogueRow(
            owner, source, None, "anchor_required",
            "composite record has no frozen reviewed fragment anchor",
            _mid_controls(record),
        )
    try:
        compiled = compile_anchored_record(source, fragments, glyphs)
    except EnglishDialogueCompileError as error:
        return CompiledDialogueRow(
            owner, source, None, "compile_error", str(error), _mid_controls(record)
        )
    return CompiledDialogueRow(
        owner,
        source,
        compiled,
        "composite_anchored",
        f"compiled with continuation {continuation.entry_id} and exact opcode-3D control",
        _mid_controls(record),
    )


def compile_direct_rows(
    payload: bytes,
    rows: Iterable[DefinitiveScriptRow],
    glyphs: EnglishGlyphTable,
) -> tuple[CompiledDialogueRow, ...]:
    """Compile rows in workbook order, resolving registered composite records."""

    ordered = tuple(rows)
    by_id = {row.entry_id: row for row in ordered}
    result: list[CompiledDialogueRow] = []
    for row in ordered:
        if row.entry_id in CONTINUATION_IDS:
            result.append(
                CompiledDialogueRow(
                    row,
                    None,
                    None,
                    "composite_continuation",
                    "compiled as part of its registered physical owner record",
                )
            )
            continue
        spec = BY_OWNER_ID.get(row.entry_id)
        if spec is not None:
            continuation = by_id.get(spec.continuation_id)
            if continuation is None:
                result.append(
                    CompiledDialogueRow(
                        row,
                        None,
                        None,
                        "composite_mapping_error",
                        f"missing continuation row {spec.continuation_id}",
                    )
                )
            else:
                result.append(
                    _compile_composite_row(payload, row, continuation, glyphs)
                )
            continue
        result.append(compile_direct_row(payload, row, glyphs))
    return tuple(result)


def summarize_compilation(
    rows: Iterable[CompiledDialogueRow],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return dict(sorted(counts.items()))
