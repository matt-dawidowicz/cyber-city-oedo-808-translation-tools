"""Regression coverage for auxiliary-text dialogue-shadow suppression."""

from __future__ import annotations

import csv
import pathlib
import tempfile
import unittest

from cyber_oedo.analysis.build_resource_map import OUTPUT_FIELDS as RESOURCE_FIELDS
from cyber_oedo.analysis.scan_likely_sjis import OUTPUT_FIELDS as LIKELY_FIELDS
from cyber_oedo.contracts import DIALOGUE_V1
from cyber_oedo.text.extract_auxiliary_text import write_auxiliary_text


def write_tsv(
    path: pathlib.Path,
    fields: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    """Write one small UTF-8-SIG TSV fixture."""

    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path: pathlib.Path) -> list[dict[str, str]]:
    """Read one small UTF-8-SIG TSV fixture."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def resource_row(
    *,
    start: int = 0,
    end: int = 4096,
    name: str = "TEST",
) -> dict[str, object]:
    """Return one candidate-resource map row."""

    return {
        "resource_sector": start // 2048,
        "resource_offset": f"0x{start:08X}",
        "resource_name": name,
        "end_sector_exclusive": end // 2048,
        "end_offset_exclusive": f"0x{end:08X}",
        "sector_count": (end - start) // 2048,
        "byte_count": end - start,
        "bank": "MISSION_0",
        "boundary_source": "next_candidate_header",
        "ownership_status": "unproven",
    }


def dialogue_row(
    start: int,
    raw: bytes,
    tagged_text: str,
    text: str,
) -> dict[str, object]:
    """Return one structured-dialogue row matching *raw*."""

    return {
        "bank": "MISSION_0",
        "quality": "likely_text",
        "offset": f"0x{start:08X}",
        "sector": start // 2048,
        "within_sector": f"0x{start % 2048:03X}",
        "record_bytes": len(raw),
        "sjis_characters": len(text),
        "controls": "40" if "<$40>" in tagged_text else "",
        "tagged_text": tagged_text,
        "text": text,
        "raw_hex": raw.hex(" "),
    }


def likely_row(start: int, text: str) -> dict[str, object]:
    """Return one broad Shift-JIS candidate row."""

    raw = text.encode("shift_jis")
    return {
        "offset": f"0x{start:08X}",
        "sector": start // 2048,
        "within_sector": f"0x{start % 2048:03X}",
        "bytes": len(raw),
        "characters": len(text),
        "hiragana": 0,
        "katakana": 0,
        "kanji": 4,
        "fullwidth": 0,
        "text": text,
    }


class AuxiliaryDialogueShadowTests(unittest.TestCase):
    """Prevent broad-scan substrings from becoming translator-facing rows."""

    def _run_fixture(
        self,
        *,
        tagged_text: str = "男「これは完全な文章です」",
        visible_text: str = "男「これは完全な文章です」",
        raw_body: bytes | None = None,
        candidate_text: str = "完全な文章",
        candidate_offset: int = 0x300,
        shadow_distance: int = 2048,
    ) -> tuple[object, list[dict[str, str]], list[dict[str, str]]]:
        """Run one synthetic source-guarded extraction and return its outputs."""

        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            rejected = root / "rejected.tsv"

            dialogue_offset = 0x100
            body = raw_body if raw_body is not None else visible_text.encode("shift_jis")
            dialogue_raw = b"\x27\x28" + body + b"\x00"
            candidate_raw = candidate_text.encode("shift_jis")
            payload_size = max(4096, candidate_offset + len(candidate_raw) + 1)
            data = bytearray(payload_size)
            data[:4] = b"TEST"
            data[dialogue_offset : dialogue_offset + len(dialogue_raw)] = dialogue_raw
            data[candidate_offset : candidate_offset + len(candidate_raw)] = candidate_raw

            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row(end=payload_size)])
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [dialogue_row(dialogue_offset, dialogue_raw, tagged_text, visible_text)],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(candidate_offset, candidate_text)])

            stats = write_auxiliary_text(
                likely,
                dialogue,
                auxiliary,
                resource_map=resource_map,
                data=bytes(data),
                rejected_output=rejected,
                shadow_distance=shadow_distance,
            )
            return stats, read_tsv(auxiliary), read_tsv(rejected)

    def test_nearby_proper_dialogue_fragment_is_rejected(self) -> None:
        stats, auxiliary, rejected = self._run_fixture()
        self.assertEqual(stats.dialogue_shadows, 1)
        self.assertEqual(auxiliary, [])
        self.assertEqual(rejected[0]["rejection_reason"], "nearby_dialogue_fragment")
        self.assertEqual(rejected[0]["resource_name"], "TEST")
        self.assertEqual(rejected[0]["matched_dialogue_offset"], "0x00000100")

    def test_exact_duplicate_string_is_retained(self) -> None:
        full = "男「これは完全な文章です」"
        stats, auxiliary, rejected = self._run_fixture(candidate_text=full)
        self.assertEqual(stats.dialogue_shadows, 0)
        self.assertEqual(len(auxiliary), 1)
        self.assertEqual(rejected, [])

    def test_match_may_not_cross_dialogue_control_boundary(self) -> None:
        left = "男「これは完全".encode("shift_jis")
        right = "な文章です」".encode("shift_jis")
        stats, auxiliary, rejected = self._run_fixture(
            tagged_text="男「これは完全<$40>な文章です」",
            visible_text="男「これは完全な文章です」",
            raw_body=left + b"\x40" + right,
        )
        self.assertEqual(stats.dialogue_shadows, 0)
        self.assertEqual(len(auxiliary), 1)
        self.assertEqual(rejected, [])

    def test_distant_substring_coincidence_is_retained(self) -> None:
        stats, auxiliary, rejected = self._run_fixture(
            candidate_offset=0xC00,
            shadow_distance=100,
        )
        self.assertEqual(stats.dialogue_shadows, 0)
        self.assertEqual(len(auxiliary), 1)
        self.assertEqual(rejected, [])

    def test_same_text_fragment_in_different_resource_is_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            rejected = root / "rejected.tsv"
            dialogue_text = "これは完全な文章です"
            fragment = "完全な文章"
            dialogue_raw = b"\x27\x28" + dialogue_text.encode("shift_jis") + b"\x00"
            fragment_raw = fragment.encode("shift_jis")
            data = bytearray(4096)
            data[:5] = b"FIRST"
            data[2048 : 2048 + 6] = b"SECOND"
            data[0x100 : 0x100 + len(dialogue_raw)] = dialogue_raw
            data[0x900 : 0x900 + len(fragment_raw)] = fragment_raw
            write_tsv(
                resource_map,
                RESOURCE_FIELDS,
                [
                    resource_row(start=0, end=2048, name="FIRST"),
                    resource_row(start=2048, end=4096, name="SECOND"),
                ],
            )
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [dialogue_row(0x100, dialogue_raw, dialogue_text, dialogue_text)],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(0x900, fragment)])
            stats = write_auxiliary_text(
                likely,
                dialogue,
                auxiliary,
                resource_map=resource_map,
                data=bytes(data),
                rejected_output=rejected,
            )
            self.assertEqual(stats.dialogue_shadows, 0)
            self.assertEqual(len(read_tsv(auxiliary)), 1)
            self.assertEqual(read_tsv(rejected), [])

    def test_short_zero_tail_does_not_suppress_legitimate_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            rejected = root / "rejected.tsv"
            dialogue_text = "これは完全な文章です"
            fragment = "完全な文章"
            dialogue_raw = b"\x27\x28" + dialogue_text.encode("shift_jis") + b"\x00"
            fragment_raw = fragment.encode("shift_jis")
            data = bytearray(4096)
            data[:4] = b"TEST"
            data[0x100 : 0x100 + len(dialogue_raw)] = dialogue_raw
            data[0x300 : 0x300 + len(fragment_raw)] = fragment_raw
            data[0x300 + len(fragment_raw) + 4] = 0x33
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row()])
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [dialogue_row(0x100, dialogue_raw, dialogue_text, dialogue_text)],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(0x300, fragment)])
            stats = write_auxiliary_text(
                likely,
                dialogue,
                auxiliary,
                resource_map=resource_map,
                data=bytes(data),
                rejected_output=rejected,
            )
            self.assertEqual(stats.dialogue_shadows, 0)
            self.assertEqual(len(read_tsv(auxiliary)), 1)
            self.assertEqual(read_tsv(rejected), [])

    def test_dangling_sjis_lead_before_zero_tail_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            rejected = root / "rejected.tsv"
            dialogue_text = "これは完全な文章です"
            fragment = "完全な文章"
            dialogue_raw = b"\x27\x28" + dialogue_text.encode("shift_jis") + b"\x00"
            fragment_raw = fragment.encode("shift_jis")
            end = 0x300 + len(fragment_raw)
            data = bytearray(4096)
            data[:4] = b"TEST"
            data[0x100 : 0x100 + len(dialogue_raw)] = dialogue_raw
            data[0x300:end] = fragment_raw
            data[end] = 0x82
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row()])
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [dialogue_row(0x100, dialogue_raw, dialogue_text, dialogue_text)],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(0x300, fragment)])
            stats = write_auxiliary_text(
                likely,
                dialogue,
                auxiliary,
                resource_map=resource_map,
                data=bytes(data),
                rejected_output=rejected,
            )
            self.assertEqual(stats.dialogue_shadows, 1)
            rows = read_tsv(rejected)
            self.assertEqual(rows[0]["dangling_lead_byte"], "0x82")
            self.assertGreaterEqual(int(rows[0]["tail_zero_bytes"]), 32)

    def test_stale_likely_scan_fails_source_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            text = "完全な文章"
            dialogue_text = "これは完全な文章です"
            dialogue_raw = b"\x27\x28" + dialogue_text.encode("shift_jis") + b"\x00"
            data = bytearray(4096)
            data[:4] = b"TEST"
            data[0x100 : 0x100 + len(dialogue_raw)] = dialogue_raw
            candidate_raw = text.encode("shift_jis")
            data[0x300 : 0x300 + len(candidate_raw)] = candidate_raw
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row()])
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [dialogue_row(0x100, dialogue_raw, dialogue_text, dialogue_text)],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(0x300, text)])
            data[0x300] ^= 0x01
            with self.assertRaisesRegex(ValueError, "candidate source mismatch"):
                write_auxiliary_text(
                    likely,
                    dialogue,
                    auxiliary,
                    resource_map=resource_map,
                    data=bytes(data),
                )

    def test_stale_dialogue_fails_source_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            text = "完全な文章"
            dialogue_text = "これは完全な文章です"
            dialogue_raw = b"\x27\x28" + dialogue_text.encode("shift_jis") + b"\x00"
            data = bytearray(4096)
            data[:4] = b"TEST"
            data[0x100 : 0x100 + len(dialogue_raw)] = dialogue_raw
            candidate_raw = text.encode("shift_jis")
            data[0x300 : 0x300 + len(candidate_raw)] = candidate_raw
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row()])
            bad_dialogue_raw = bytearray(dialogue_raw)
            bad_dialogue_raw[2] ^= 0x01
            write_tsv(
                dialogue,
                DIALOGUE_V1.fields,
                [
                    dialogue_row(
                        0x100,
                        bytes(bad_dialogue_raw),
                        dialogue_text,
                        dialogue_text,
                    )
                ],
            )
            write_tsv(likely, LIKELY_FIELDS, [likely_row(0x300, text)])
            with self.assertRaisesRegex(ValueError, "dialogue source mismatch"):
                write_auxiliary_text(
                    likely,
                    dialogue,
                    auxiliary,
                    resource_map=resource_map,
                    data=bytes(data),
                )

    def test_stale_resource_map_fails_source_guard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            data = bytearray(4096)
            data[:4] = b"TEST"
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row(name="WRONG")])
            write_tsv(dialogue, DIALOGUE_V1.fields, [])
            write_tsv(likely, LIKELY_FIELDS, [])
            with self.assertRaisesRegex(ValueError, "resource source mismatch"):
                write_auxiliary_text(
                    likely,
                    dialogue,
                    auxiliary,
                    resource_map=resource_map,
                    data=bytes(data),
                )

    def test_likely_scan_must_remain_offset_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            resource_map = root / "resource.tsv"
            dialogue = root / "dialogue.tsv"
            likely = root / "likely.tsv"
            auxiliary = root / "auxiliary.tsv"
            data = bytearray(4096)
            data[:4] = b"TEST"
            first = "最初の文章"
            second = "次の文章です"
            first_raw = first.encode("shift_jis")
            second_raw = second.encode("shift_jis")
            data[0x300 : 0x300 + len(first_raw)] = first_raw
            data[0x200 : 0x200 + len(second_raw)] = second_raw
            write_tsv(resource_map, RESOURCE_FIELDS, [resource_row()])
            write_tsv(dialogue, DIALOGUE_V1.fields, [])
            write_tsv(
                likely,
                LIKELY_FIELDS,
                [likely_row(0x300, first), likely_row(0x200, second)],
            )
            with self.assertRaisesRegex(ValueError, "candidate rows are not sorted"):
                write_auxiliary_text(
                    likely,
                    dialogue,
                    auxiliary,
                    resource_map=resource_map,
                    data=bytes(data),
                )


if __name__ == "__main__":
    unittest.main()
