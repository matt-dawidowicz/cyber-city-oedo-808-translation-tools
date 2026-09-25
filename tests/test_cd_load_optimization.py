from __future__ import annotations

import unittest

from cyber_oedo.runtime.cd_load_optimization import (
    HOT_ASSETS,
    PackBitsError,
    find_fixed_vsync_waits,
    packbits_words,
    summarize_source_layout,
    unpackbits_words,
)


class WordPackBitsTests(unittest.TestCase):
    def test_round_trip_mixed_words(self) -> None:
        source = (
            b"AB" * 12
            + b"CD" + b"EF" + b"GH"
            + b"IJ" * 3
            + bytes(range(32))
        )
        encoded = packbits_words(source)
        self.assertEqual(unpackbits_words(encoded, len(source)), source)

    def test_long_repeat_is_split_at_128_words(self) -> None:
        source = b"XY" * 300
        encoded = packbits_words(source)
        self.assertEqual(unpackbits_words(encoded, len(source)), source)
        self.assertLess(len(encoded), 20)

    def test_odd_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackBitsError, "even"):
            packbits_words(b"abc")

    def test_reserved_control_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackBitsError, "reserved"):
            unpackbits_words(bytes((128,)))

    def test_fixed_vsync_wait_signature_reports_frame_count(self) -> None:
        payload = bytes.fromhex("EA EA A0 78 20 7B E0 88 D0 FA EA")
        waits = find_fixed_vsync_waits(payload)
        self.assertEqual(len(waits), 1)
        self.assertEqual(waits[0]["payload_offset"], "0x00000002")
        self.assertEqual(waits[0]["frames"], 120)
        self.assertEqual(waits[0]["seconds_at_60hz"], 2.0)

    def test_fixed_vsync_wait_at_payload_end_is_detected(self) -> None:
        payload = bytes.fromhex("A0 78 20 7B E0 88 D0 FA")
        waits = find_fixed_vsync_waits(payload)
        self.assertEqual(len(waits), 1)
        self.assertEqual(waits[0]["payload_offset"], "0x00000000")
        self.assertEqual(waits[0]["frames"], 120)

    def test_main_scene_source_layout_uses_post_transfer_gaps(self) -> None:
        assets = tuple(
            item
            for item in HOT_ASSETS
            if item.name in {
                "main_scene_local_a",
                "main_scene_local_b",
                "main_scene_vram",
            }
        )
        report = summarize_source_layout(assets)
        self.assertEqual(report["post_transfer_gaps_sectors"], [73, 7])
        self.assertEqual(report["gap_sectors_total"], 80)
        self.assertEqual(report["span_start_lba"], "0x228E")
        self.assertEqual(report["span_end_lba_inclusive"], "0x2305")
        self.assertEqual(report["span_sectors"], 120)
        self.assertEqual(report["transfer_sectors"], 40)
        self.assertAlmostEqual(report["transfer_density_percent"], 100.0 / 3.0)



if __name__ == "__main__":
    unittest.main()
