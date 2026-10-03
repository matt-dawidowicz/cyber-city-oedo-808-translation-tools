"""Mission-scoped authored VWF dialogue compiler.

Ordinary authored dialogue is promoted to the VWF stream format while records
with reviewed mid-text controls remain on the fixed native-English path.  One
compiler instance owns one shared VWF token dictionary for the entire mission.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.script import ControlCommand, TextRun, parse_dialogue_record
from cyber_oedo.script.opcodes import DIALOGUE_MARKER, DialogueOpcode
from cyber_oedo.text.english_dialogue_engine import (
    EnglishDialogueCompileError,
    EnglishGlyphTable,
)
from cyber_oedo.text.vwf_cells import (
    VWF_MODE_SIGNATURE,
    VWF_SEGMENT_END_TOKEN,
    VwfCellDictionary,
    VwfDictionaryBuilder,
    encode_vwf_token,
    pack_vwf_line,
    render_vwf_dictionary,
)
from cyber_oedo.text.vwf_text import LINE_PIXELS, VwfFont, wrap_vwf


class VwfDialogueCompileError(ValueError):
    pass


def _boundary_controls(source_record: bytes) -> tuple[bytes, bytes, bool]:
    record = parse_dialogue_record(source_record, 0)
    if record is None or record.byte_count != len(source_record):
        raise VwfDialogueCompileError("source record is not valid dialogue bytecode")
    nodes = record.body.nodes
    text_indices = [i for i, node in enumerate(nodes) if isinstance(node, TextRun)]
    if not text_indices:
        raise VwfDialogueCompileError("dialogue record contains no visible text")
    first = min(text_indices)
    last = max(text_indices)
    leading = bytearray()
    trailing = bytearray()
    has_mid_semantic = False
    for index, node in enumerate(nodes):
        if not isinstance(node, ControlCommand):
            continue
        if node.opcode == int(DialogueOpcode.PAGE_BREAK):
            continue
        if index < first:
            leading.extend(node.raw)
        elif index > last:
            trailing.extend(node.raw)
        else:
            before = any(isinstance(item, TextRun) for item in nodes[:index])
            after = any(isinstance(item, TextRun) for item in nodes[index + 1 :])
            if before and after:
                has_mid_semantic = True
    return bytes(leading), bytes(trailing), has_mid_semantic


@dataclass(slots=True)
class VwfMissionDialogueCompiler:
    font: VwfFont
    glyphs: EnglishGlyphTable

    def __post_init__(self) -> None:
        if self.font.characters != self.glyphs.characters:
            raise VwfDialogueCompileError(
                "VWF font and native glyph table must use identical character order"
            )
        self._dictionary = VwfDictionaryBuilder()

    def _encode_line(self, line: str) -> bytes:
        compiled = pack_vwf_line(line, self.font, self.glyphs, self._dictionary)
        out = bytearray(VWF_MODE_SIGNATURE)
        for token in compiled.tokens:
            out.extend(encode_vwf_token(token))
        out.extend(VWF_SEGMENT_END_TOKEN.to_bytes(2, "big"))
        return bytes(out)

    def compile_automatic_record(self, source_record: bytes, english: str) -> bytes:
        """Compile one control-safe authored record into VWF line segments."""

        leading, trailing, has_mid_semantic = _boundary_controls(source_record)
        if has_mid_semantic:
            raise VwfDialogueCompileError(
                "mid-text semantic controls must use the frozen fixed-renderer path"
            )
        try:
            lines = wrap_vwf(english, self.font, max_pixels=LINE_PIXELS)
        except Exception as error:
            raise VwfDialogueCompileError(str(error)) from error

        body = bytearray(leading)
        for index, line in enumerate(lines):
            body.extend(self._encode_line(line))
            if index < len(lines) - 1:
                body.append(int(DialogueOpcode.PAGE_BREAK))
        body.extend(trailing)
        body.append(0)
        return DIALOGUE_MARKER + bytes(body)

    @property
    def dictionary(self) -> VwfCellDictionary:
        return self._dictionary.finish()

    @property
    def staged_cells(self) -> bytes:
        return render_vwf_dictionary(self.dictionary, self.font)


__all__ = [
    "VwfDialogueCompileError",
    "VwfMissionDialogueCompiler",
]
