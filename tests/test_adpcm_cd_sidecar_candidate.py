"""Fail-closed research constraints for the PC Engine CD-sidecar candidate."""

import hashlib
import unittest

from cyber_oedo.runtime.adpcm_cd_sidecar_candidate import (
    ORIGINAL_ADPCM_LENGTH, ORIGINAL_ADPCM_SHA256,
    SIDECAR_CARD_RAM_BANK, SIDECAR_EXEC_CPU, SIDECAR_LBA,
    SIDECAR_PAYLOAD_OFFSET, SIDECAR_RELATIVE_SECTOR,
    build_cd_sidecar_stub, build_cd_sidecar_sector,
    build_unverified_cd_sidecar_candidate,
)
from cyber_oedo.runtime.engine_polish_pilot import (
    QUARANTINED_ADPCM_PROFILES, build_intro_smoke_polish_patches,
)


# Authenticated 56-byte original command as machine-code signature only.
# No original copyrighted game image / media are distributed.
STOCK_COMMAND = bytes.fromhex(
    "20 42 e0 20 1a 86 aa d0 fa ad dd 8f f0 29 0a 18 "
    "6d dd 8f aa bd 8b 8b 85 fc bd 8c 8b 85 fe bd 8d "
    "8b 85 fd a9 04 85 f8 64 ff a9 00 85 fa a9 e0 "
    "85 fb 20 33 e0 aa d0 c9 60"
)


class AdpcmCdSidecarTests(unittest.TestCase):
    def test_cd_sector_and_card_ram_bank_are_separate(self):
        self.assertEqual(SIDECAR_RELATIVE_SECTOR, 41190)
        self.assertEqual(SIDECAR_LBA, 0xAEEC)
        self.assertEqual(SIDECAR_CARD_RAM_BANK, 0x75)
        self.assertEqual(SIDECAR_EXEC_CPU, 0x6000)
        self.assertEqual(SIDECAR_PAYLOAD_OFFSET, 41190 * 2048)

    def test_original_source_command_is_exact(self):
        self.assertEqual(len(STOCK_COMMAND), ORIGINAL_ADPCM_LENGTH)
        self.assertEqual(
            hashlib.sha256(STOCK_COMMAND).hexdigest(), ORIGINAL_ADPCM_SHA256
        )

    def test_relocated_command_keeps_relative_branches(self):
        sector = build_cd_sidecar_sector(STOCK_COMMAND)
        self.assertEqual(len(sector), 2048)
        self.assertEqual(sector[:7], STOCK_COMMAND[:7])
        self.assertEqual(sector[0x31:0x34], bytes.fromhex("20 38 60"))
        for index in (7, 12, 53):
            self.assertEqual(sector[index], STOCK_COMMAND[index])
        self.assertEqual(
            sector[56:64], bytes.fromhex("43 20 48 43 40 48 A9 6B")
        )
        self.assertEqual(sector[151:], bytes(2048 - 151))

    def test_in_place_loader_fits_exactly(self):
        stub = build_cd_sidecar_stub()
        self.assertEqual(len(stub), ORIGINAL_ADPCM_LENGTH)
        self.assertEqual(stub[:7], bytes.fromhex("43 20 48 A9 75 53 20"))
        self.assertIn(bytes.fromhex("20 09 E0"), stub)
        self.assertIn(bytes.fromhex("20 00 60"), stub)
        self.assertEqual(stub[-1], 0xEA)

    def test_build_refuses_non_source_and_missing_acknowledgment(self):
        with self.assertRaisesRegex(ValueError, "unsafe research"):
            build_unverified_cd_sidecar_candidate(b"not source")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            build_unverified_cd_sidecar_candidate(
                b"not source", acknowledge_unsafe_research=True
            )
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            build_cd_sidecar_sector(bytes(56))

    def test_normal_adpcm_profiles_stay_quarantined(self):
        self.assertEqual(
            QUARANTINED_ADPCM_PROFILES,
            frozenset({"adpcm", "portrait-adpcm", "all-seven"}),
        )
        for profile in QUARANTINED_ADPCM_PROFILES:
            with self.subTest(profile=profile):
                with self.assertRaisesRegex(ValueError, "cross-overlay ADPCM"):
                    build_intro_smoke_polish_patches(profile)


if __name__ == "__main__":
    unittest.main()
