"""Regression tests for stock-renderer relocation safety."""

from __future__ import annotations

import unittest

from cyber_oedo.text.dialogue_relocation import (
    DIALOGUE_MARKER,
    DialoguePage,
    DialogueRelocationPlan,
    PageBreakPlan,
    PageGeometry,
    PointerSite,
    RelocationArea,
    ascii_to_fullwidth_sjis,
    find_u16_pointer_candidates,
    wrap_dialogue_page,
)
from cyber_oedo.text.extract_dialogue import parse_record


class DialogueRelocationTests(unittest.TestCase):
    """Protect conservative stock-renderer relocation contracts."""

    @staticmethod
    def page_only_source() -> bytes:
        """Return a synthetic two-page Shift-JIS dialogue record."""

        return (
            DIALOGUE_MARKER
            + "一頁".encode("shift_jis")
            + b"\x40"
            + "二頁".encode("shift_jis")
            + b"\x00"
        )

    def test_page_plan_preserves_existing_control(self) -> None:
        """Compile English without introducing an experimental escape."""

        geometry = PageGeometry(width=11, maximum_lines=3)
        plan = PageBreakPlan(
            pages=(
                DialoguePage(("Accurate", "English.")),
                wrap_dialogue_page("Second page.", geometry),
            ),
            source_page_breaks=1,
            geometry=geometry,
        )
        compiled = plan.compile_record(self.page_only_source())
        parsed = parse_record(compiled, len(DIALOGUE_MARKER))
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.controls, (0x40,))
        self.assertIn(ascii_to_fullwidth_sjis("Accurate"), compiled)
        self.assertNotIn(b"\xFF", compiled)
        self.assertNotIn(b"\xFE", compiled)

    def test_added_pages_require_explicit_opt_in(self) -> None:
        """Reject silent paging expansion."""

        pages = tuple(DialoguePage(((word + "."),)) for word in ("One", "Two", "Three"))
        geometry = PageGeometry(width=11, maximum_lines=3)
        with self.assertRaises(ValueError):
            PageBreakPlan(
                pages=pages,
                source_page_breaks=1,
                geometry=geometry,
            )
        plan = PageBreakPlan(
            pages=pages,
            source_page_breaks=1,
            geometry=geometry,
            allow_added_page_breaks=True,
        )
        parsed = parse_record(
            plan.compile_record(self.page_only_source()),
            len(DIALOGUE_MARKER),
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.controls, (0x40, 0x40))

    def test_mixed_control_stream_is_rejected(self) -> None:
        """Keep wait/input controls out of a page-only compiler."""

        source = (
            DIALOGUE_MARKER
            + "一".encode("shift_jis")
            + b"\x21"
            + "二".encode("shift_jis")
            + b"\x00"
        )
        plan = PageBreakPlan(
            pages=(DialoguePage(("English.",)),),
            source_page_breaks=0,
            geometry=PageGeometry(width=11, maximum_lines=3),
        )
        with self.assertRaises(ValueError):
            plan.compile_record(source)

    def test_relocation_requires_proven_pointer(self) -> None:
        """Refuse a destination that has no proven reachability."""

        source = self.page_only_source()
        area = RelocationArea(
            offset=0x1200,
            expected=b"\x00" * 64,
            resource_start=0x1000,
            resource_end=0x1300,
            alignment=1,
            purpose="synthetic owned area",
        )
        with self.assertRaises(ValueError):
            DialogueRelocationPlan(
                source_offset=0x1080,
                source_record=source,
                replacement_record=source,
                area=area,
                pointers=(),
                purpose="unmapped dialogue",
            )

    def test_relocation_updates_all_proven_pointers(self) -> None:
        """Guard source bytes and update every mapped pointer."""

        source = self.page_only_source()
        area = RelocationArea(
            offset=0x1200,
            expected=b"\x00" * 64,
            resource_start=0x1000,
            resource_end=0x1300,
            alignment=2,
            purpose="synthetic confirmed resource tail",
        )
        pointers = (
            PointerSite(0x1010, 0x1000, 0x1080, "table entry A"),
            PointerSite(0x1014, 0x1000, 0x1080, "table entry B"),
        )
        plan = DialogueRelocationPlan(
            source_offset=0x1080,
            source_record=source,
            replacement_record=source,
            area=area,
            pointers=pointers,
            purpose="synthetic dialogue",
        )
        source_guard, first, second, destination = plan.to_payload_patches()
        self.assertEqual(source_guard.expected, source_guard.replacement)
        self.assertEqual(first.expected, bytes.fromhex("80 00"))
        self.assertEqual(first.replacement, bytes.fromhex("00 02"))
        self.assertEqual(second.replacement, bytes.fromhex("00 02"))
        self.assertEqual(len(destination.expected), len(destination.replacement))

    def test_pointer_scan_is_only_candidate_discovery(self) -> None:
        """Return aligned byte matches without promoting them to proof."""

        data = bytearray(64)
        data[8:10] = bytes.fromhex("20 00")
        data[20:22] = bytes.fromhex("20 00")
        self.assertEqual(
            find_u16_pointer_candidates(
                bytes(data),
                target_offset=0x1020,
                base_offset=0x1000,
                search_start=0,
                search_end=len(data),
                alignment=2,
            ),
            (8, 20),
        )


if __name__ == "__main__":
    unittest.main()
