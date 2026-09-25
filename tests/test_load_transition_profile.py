from __future__ import annotations

import unittest

from cyber_oedo.runtime.load_transition_profile import (
    build_transition_latency_report,
    find_m0_dialogue_load_windows,
)


HISTORICAL_SHAPE = """
[CD_READ 001 B01] frame=220 sector=$001425 track2_payload_off=$00A12800 type=$01(LOCAL_SECTORS) dest=$8000 len=$0001_sectors
[CD_READ 002 B01] frame=287 sector=$001426 track2_payload_off=$00A13000 type=$01(LOCAL_SECTORS) dest=$29D0 len=$0001_sectors
[CD_READ 003 B01] frame=298 sector=$0010DD track2_payload_off=$0086E800 type=$01(LOCAL_SECTORS) dest=$29D0 len=$0001_sectors
[CD_READ 004 B02] frame=449 sector=$001441 track2_payload_off=$00A20800 type=$01(LOCAL_SECTORS) dest=$9000 len=$0002_sectors
[CD_READ 005 B02] frame=493 sector=$001458 track2_payload_off=$00A2C000 type=$FE(VRAM_BYTES) dest=$4000 len=$2020_bytes
DIALOGUE GROUP 1 START frame=590
"""


class LoadTransitionProfileTests(unittest.TestCase):
    def test_finds_cross_burst_dialogue_load(self) -> None:
        windows = find_m0_dialogue_load_windows(HISTORICAL_SHAPE)
        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertEqual(window.load_to_ready_frames, 370)
        self.assertEqual(window.transfer_sectors, 10)
        self.assertEqual(
            window.source_start_deltas,
            (1, -0x349, 0x364, 0x17),
        )
        self.assertEqual(window.absolute_seek_distance, 1729)

    def test_reports_six_second_load_for_ten_sector_stream(self) -> None:
        report = build_transition_latency_report(HISTORICAL_SHAPE)
        self.assertEqual(report["minimum_frames"], 370)
        self.assertAlmostEqual(report["mean_seconds"], 370 / 60)
        floor = report["streaming_floor"]
        self.assertEqual(floor["sectors"], 10)
        self.assertAlmostEqual(floor["seconds_at_1x"], 10 / 75)
        self.assertGreater(
            report["mean_excess_seconds_over_stream_floor"],
            5.9,
        )

    def test_rejects_similar_but_wrong_resource_shape(self) -> None:
        wrong = HISTORICAL_SHAPE.replace("sector=$001441", "sector=$001442")
        self.assertEqual(find_m0_dialogue_load_windows(wrong), ())

    def test_requires_dialogue_ready_marker(self) -> None:
        no_ready = HISTORICAL_SHAPE.replace(
            "DIALOGUE GROUP 1 START frame=590",
            "",
        )
        self.assertEqual(find_m0_dialogue_load_windows(no_ready), ())


if __name__ == "__main__":
    unittest.main()
