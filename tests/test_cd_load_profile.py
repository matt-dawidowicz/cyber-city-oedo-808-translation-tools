from __future__ import annotations

import unittest

from cyber_oedo.runtime.cd_load_profile import (
    build_cd_load_report,
    parse_cd_read_log,
)


SAMPLE = """
[CD_READ 001 B01] frame=100 sector=$00228E track2_payload_off=$01147000 type=$01(LOCAL_SECTORS) dest=$4000 len=$0007_sectors dest_page_bank=$80
[CD_READ 002 B01] frame=135 sector=$0022DE track2_payload_off=$0116F000 type=$01(LOCAL_SECTORS) dest=$9000 len=$0003_sectors dest_page_bank=$82
[CD_READ 003 B01] frame=190 sector=$0022E8 track2_payload_off=$01174000 type=$FE(VRAM_BYTES) dest=$0900 len=$EE00_bytes dest_page_bank=$FF
[CD_READ 004 B02] frame=500 sector=$00228E track2_payload_off=$01147000 type=$01(LOCAL_SECTORS) dest=$4000 len=$0007_sectors dest_page_bank=$80
[CD_READ 005 B02] frame=535 sector=$0022DE track2_payload_off=$0116F000 type=$01(LOCAL_SECTORS) dest=$9000 len=$0103_sectors dest_page_bank=$82
[CD_READ 006 B02] frame=590 sector=$0022E8 track2_payload_off=$01174000 type=$FE(VRAM_BYTES) dest=$0900 len=$EE00_bytes dest_page_bank=$FF
"""


class CdLoadProfileTests(unittest.TestCase):
    def test_historical_sector_length_artifact_is_normalized(self) -> None:
        reads = parse_cd_read_log(SAMPLE)
        self.assertEqual(reads[4].length, 3)
        self.assertEqual(reads[4].transfer_bytes, 6144)

    def test_repeated_bundle_is_identified(self) -> None:
        report = build_cd_load_report(SAMPLE)
        self.assertEqual(report["read_count"], 6)
        self.assertEqual(report["burst_count"], 2)
        self.assertEqual(len(report["repeated_bundles"]), 1)
        bundle = report["repeated_bundles"][0]
        self.assertEqual(bundle["count"], 2)
        self.assertEqual(bundle["observed_frame_spans"], [90, 90])
        self.assertEqual(bundle["transfer_bytes_per_bundle"], 81408)

    def test_repeat_bytes_are_separate_from_unique_signatures(self) -> None:
        report = build_cd_load_report(SAMPLE)
        self.assertEqual(report["total_transfer_bytes"], 162816)
        self.assertEqual(report["unique_signature_bytes"], 81408)
        self.assertEqual(report["repeat_extra_bytes"], 81408)
        self.assertAlmostEqual(report["repeat_extra_percent_of_transfer"], 50.0)

    def test_empty_log_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "no CD_READ"):
            build_cd_load_report("nothing here")


if __name__ == "__main__":
    unittest.main()
