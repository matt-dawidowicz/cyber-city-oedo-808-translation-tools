from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from cyber_oedo.resources import kuruzer

BODY = b"\x81\x75\x89\xb4\x40\x82\xcc\x96\xbc"
NARRATION = kuruzer.DIALOGUE_MARKER + BODY + b"\x00"
RESOURCE = (
    b"H" * kuruzer.NARRATION_START
    + NARRATION
    + b"\x00" * (kuruzer.NARRATION_END - kuruzer.NARRATION_START - len(NARRATION))
    + b"T" * (kuruzer.KURUZER_LENGTH - kuruzer.NARRATION_END)
)


def authentic():
    """Treat the synthetic resource and its narration span as authenticated."""

    return mock.patch.multiple(
        kuruzer,
        KURUZER_SHA256=hashlib.sha256(RESOURCE).hexdigest(),
        NARRATION_SHA256=hashlib.sha256(
            RESOURCE[kuruzer.NARRATION_START : kuruzer.NARRATION_END]
        ).hexdigest(),
    )


class NarrationRecordTests(unittest.TestCase):
    def test_accepts_glyphs_and_page_controls(self) -> None:
        kuruzer.validate_narration_record(NARRATION)

    def test_rejects_malformed_records(self) -> None:
        for record, message in (
            (b"\x27\x29" + BODY + b"\x00", "start with 27 28"),
            (kuruzer.DIALOGUE_MARKER + BODY, "end with 00"),
            (kuruzer.DIALOGUE_MARKER + b"\x81\x00", "inside a two-byte glyph"),
            (kuruzer.DIALOGUE_MARKER + b"\x2f\x10\x00", "unsupported control 0x2F"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(kuruzer.KuruzerError, message):
                    kuruzer.validate_narration_record(record)


class RebuildTests(unittest.TestCase):
    def test_rebuild_replaces_only_the_narration_span(self) -> None:
        replacement = kuruzer.DIALOGUE_MARKER + b"\x82\xa0" * 600 + b"\x00"
        with authentic():
            rebuilt = kuruzer.rebuild_kuruzer(RESOURCE, replacement)
        self.assertEqual(rebuilt[: kuruzer.NARRATION_START], RESOURCE[: kuruzer.NARRATION_START])
        self.assertEqual(rebuilt[kuruzer.NARRATION_START :][: len(replacement)], replacement)
        self.assertEqual(rebuilt[-(kuruzer.KURUZER_LENGTH - kuruzer.NARRATION_END):],
                         RESOURCE[kuruzer.NARRATION_END:])

    def test_unauthenticated_resource_is_rejected(self) -> None:
        with self.assertRaisesRegex(kuruzer.KuruzerError, "authenticated source"):
            kuruzer.rebuild_kuruzer(RESOURCE, NARRATION)

    def test_doubled_record_repeats_body_across_a_page_break(self) -> None:
        span = RESOURCE[kuruzer.NARRATION_START : kuruzer.NARRATION_END]
        body = span[2:-1]
        with authentic():
            record = kuruzer.doubled_narration_record(RESOURCE)
        self.assertEqual(record, kuruzer.DIALOGUE_MARKER + body + b"\x40" + body + b"\x00")


if __name__ == "__main__":
    unittest.main()
