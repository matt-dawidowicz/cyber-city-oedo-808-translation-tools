from __future__ import annotations

import unittest

from cyber_oedo.runtime.adpcm_memory_architecture import (
    ADPCM_TRANSFER_PARAMETERS,
    BANK_MAP_SEQUENCE,
    GenericAdWriteWrapper,
    find_generic_ad_write_wrappers,
    paired_generic_wrappers,
)


class AdpcmMemoryArchitectureTests(unittest.TestCase):
    def test_generic_ad_write_wrapper_is_detected(self) -> None:
        blob = bytes.fromhex(
            "A5 17 85 FC A5 18 85 FD A5 15 85 FA A5 16 85 FB "
            "A5 19 85 F8 A5 1A 85 F9 A9 00 85 FF 20 39 E0 60"
        )
        rows = find_generic_ad_write_wrappers(blob)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].parameter_zp, (0x17,0x18,0x15,0x16,0x19,0x1A))
        self.assertEqual(rows[0].address_type, 0)

    def test_adjacent_local_vram_forms_pair(self) -> None:
        left = GenericAdWriteWrapper(0x100,1,2,3,4,5,6,0x00)
        right = GenericAdWriteWrapper(0x120,1,2,3,4,5,6,0xFF)
        pairs = paired_generic_wrappers((left, right))
        self.assertEqual(pairs, ((left, right),))

    def test_snapshot_parameter_block_is_exactly_eight_kib(self) -> None:
        self.assertIn(bytes.fromhex("A9 00 85 FC A9 E0 85 FD"), ADPCM_TRANSFER_PARAMETERS)
        self.assertIn(bytes.fromhex("A9 00 85 FA A9 A0 85 FB"), ADPCM_TRANSFER_PARAMETERS)
        self.assertIn(bytes.fromhex("A9 00 85 F8 A9 20 85 F9"), ADPCM_TRANSFER_PARAMETERS)
        self.assertTrue(ADPCM_TRANSFER_PARAMETERS.endswith(bytes.fromhex("64 FF")))

    def test_bank_mapping_sequence_uses_mpr5_and_max_mapping_plus_six(self) -> None:
        self.assertEqual(
            BANK_MAP_SEQUENCE,
            bytes.fromhex("43 20 48 AD F5 FF 18 69 06 53 20"),
        )


if __name__ == "__main__":
    unittest.main()
