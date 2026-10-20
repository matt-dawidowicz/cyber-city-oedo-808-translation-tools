"""Promote control-safe Definitive Edition dialogue to authored VWF mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cyber_oedo.text.definitive_script_compiler import (
    CompiledDialogueRow,
    DefinitiveScriptRow,
    compile_direct_rows,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.vwf_dialogue_engine import (
    VwfDialogueCompileError,
    VwfMissionDialogueCompiler,
)
from cyber_oedo.text.vwf_text import VwfFont


@dataclass(frozen=True, slots=True)
class DefinitiveVwfMissionBuild:
    bank: str
    rows: tuple[CompiledDialogueRow, ...]
    staged_cells: bytes
    dictionary_entries: int

    @property
    def vwf_records(self) -> int:
        return sum(row.status == "vwf_automatic" for row in self.rows)

    @property
    def fixed_records(self) -> int:
        return sum(
            row.compiled_record is not None and row.status != "vwf_automatic"
            for row in self.rows
        )


def compile_definitive_vwf_mission(
    payload: bytes,
    rows: Iterable[DefinitiveScriptRow],
    font: VwfFont,
    glyphs: EnglishGlyphTable,
) -> DefinitiveVwfMissionBuild:
    """Compile one mission, promoting only control-safe authored records to VWF."""

    ordered = tuple(rows)
    if not ordered:
        raise ValueError("VWF mission build requires at least one row")
    banks = {row.bank for row in ordered}
    if len(banks) != 1:
        raise ValueError("VWF mission build may contain exactly one script bank")
    bank = next(iter(banks))

    baseline = compile_direct_rows(payload, ordered, glyphs)
    vwf = VwfMissionDialogueCompiler(font, glyphs)
    promoted: list[CompiledDialogueRow] = []

    for result in baseline:
        if result.status != "automatic" or result.source_record is None:
            promoted.append(result)
            continue
        try:
            compiled = vwf.compile_automatic_record(
                result.source_record,
                result.row.english,
            )
        except VwfDialogueCompileError as error:
            promoted.append(
                CompiledDialogueRow(
                    result.row,
                    result.source_record,
                    None,
                    "vwf_compile_error",
                    str(error),
                    result.mid_controls,
                )
            )
            continue
        promoted.append(
            CompiledDialogueRow(
                result.row,
                result.source_record,
                compiled,
                "vwf_automatic",
                "control-safe authored record promoted to mission-shared VWF dictionary",
                result.mid_controls,
            )
        )

    dictionary = vwf.dictionary
    staged = vwf.staged_cells
    return DefinitiveVwfMissionBuild(
        bank=bank,
        rows=tuple(promoted),
        staged_cells=staged,
        dictionary_entries=len(dictionary.descriptors),
    )


__all__ = [
    "DefinitiveVwfMissionBuild",
    "compile_definitive_vwf_mission",
]
