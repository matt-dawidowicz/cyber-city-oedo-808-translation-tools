from __future__ import annotations

import unittest

from cyber_oedo.runtime.load_transition_profile import (
    build_transition_latency_report,
    find_m0_dialogue_load_windows,
)


COLD_SHAPE = """
[CD_READ 001 B01] frame=220 sector=$001425 track2_payload_off=$00A12800 type=$01(LOCAL_SECTORS) dest=$8000 len=$0001_sectors
[CD_READ 002 B01] frame=287 sector=$001426 track2_payload_off=$00A13000 type=$01(LOCAL_SECTORS) dest=$29D0 len=$0001_sectors
[CD_READ 003 B01] frame=298 sector=$0010DD track2_payload_off=$0086E800 type=$01(LOCAL_SECTORS) dest=$29D0 len=$0001_sectors
[CD_READ 004 B02] frame=449 sector=$001441 track2_payload_off=$00A20800 type=$01(LOCAL_SECTORS) dest=$9000 len=$0002_sectors
[CD_READ 005 B02] frame=493 sector=$001458 track2_payload_off=$00A2C000 type=$FE(VRAM_BYTES) dest=$4000 len=$2020_bytes
DIALOGUE GROUP 1 START frame=590
"""

CACHED_SHAPE = """
[CD_READ 023 B12] frame=8570 sector=$001425 track2_payload_off=$00A12800 type=$01(LOCAL_SECTORS) dest=$8000 len=$0001_sectors
[CD_READ 024 B12] frame=8637 sector=$001426 track2_payload_off=$00A13000 type=$01(LOCAL_SECTORS) dest=$29D0 len=$0001_sectors
[CD_READ 025 B13] frame=8771 sector=$001441 track2_payload_off=$00A20800 type=$01(LOCAL_SECTORS) dest=$9000 len=$0002_sectors
[CD_READ 026 B13] frame=8815 sector=$001458 track2_payload_off=$00A2C000 type=$FE(VRAM_BYTES) dest=$4000 len=$2020_bytes
DIALOGUE GROUP 5 START frame=8912
"""


class LoadTransitionProfileTests(unittest.TestCase):
    def test_finds_cold_cross_burst_dialogue_load(self) -> None:
        windows = find_m0_dialogue_load_windows(COLD_SHAPE)
        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertFalse(window.event_cache_hit)
        self.assertEqual(window.event_resource_read.sector, 0x10DD)
        self.assertEqual(window.load_to_ready_frames, 370)
        self.assertEqual(window.transfer_sectors, 10)
        self.assertEqual(
            window.source_start_deltas,
            (1, -0x349, 0x364, 0x17),
        )
        self.assertEqual(window.absolute_seek_distance, 1729)

    def test_finds_cache_hit_transition_without_event_cd_read(self) -> None:
        windows = find_m0_dialogue_load_windows(CACHED_SHAPE)
        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertTrue(window.event_cache_hit)
        self.assertIsNone(window.event_resource_read)
        self.assertEqual(window.load_to_ready_frames, 342)
        self.assertEqual(window.transfer_sectors, 9)
        self.assertEqual(window.source_start_deltas, (1, 0x1B, 0x17))
        self.assertEqual(window.absolute_seek_distance, 51)

    def test_cache_hit_proves_cold_event_seek_is_not_baseline_cause(self) -> None:
        report = build_transition_latency_report(COLD_SHAPE + CACHED_SHAPE)
        self.assertEqual(report["window_count"], 2)
        self.assertEqual(report["cold_event_resource_windows"], 1)
        self.assertEqual(report["cached_event_resource_windows"], 1)
        self.assertAlmostEqual(report["cold_mean_seconds"], 370 / 60)
        self.assertAlmostEqual(report["cached_mean_seconds"], 342 / 60)
        self.assertLess(
            report["cold_mean_seconds"] - report["cached_mean_seconds"],
            0.5,
        )

    def test_reports_large_excess_over_stream_floor(self) -> None:
        report = build_transition_latency_report(COLD_SHAPE)
        self.assertGreater(
            report["mean_excess_seconds_over_stream_floor"],
            5.9,
        )

    def test_rejects_similar_but_wrong_common_resource(self) -> None:
        wrong = COLD_SHAPE.replace("sector=$001441", "sector=$001442")
        self.assertEqual(find_m0_dialogue_load_windows(wrong), ())

    def test_requires_dialogue_ready_marker(self) -> None:
        no_ready = CACHED_SHAPE.replace(
            "DIALOGUE GROUP 5 START frame=8912",
            "",
        )
        self.assertEqual(find_m0_dialogue_load_windows(no_ready), ())


if __name__ == "__main__":
    unittest.main()
