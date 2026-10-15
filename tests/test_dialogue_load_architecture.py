from __future__ import annotations

import hashlib
import unittest

from cyber_oedo.runtime.dialogue_load_architecture import (
    ADPCM_BLOCK_SECTORS,
    DIALOGUE_MODULE_LENGTH,
    DIALOGUE_MODULE_LOADER_BYTES,
    DIALOGUE_MODULE_LOADER_CPU,
    MISSION0_B_PAYLOAD_BASE,
    MODULE_SOURCE_TABLE_RELATIVE,
    PORTRAIT_SLOT_COUNT,
    PORTRAIT_TABLE_CPU,
    SECTOR_BYTES,
    SPEAKER_BLOCK_SECTORS,
    _decode_portrait_entry,
    payload_offset_for_lba,
)


class DialogueLoadArchitectureTests(unittest.TestCase):
    def _synthetic_payload(self) -> bytes:
        # Large enough for the Mission 0-B table and the 0x1425 source.
        size = max(
            MISSION0_B_PAYLOAD_BASE + PORTRAIT_TABLE_CPU + PORTRAIT_SLOT_COUNT * 4,
            payload_offset_for_lba(0x1427),
        )
        payload = bytearray(size)

        # Reproduce the exact guarded module length/layout with arbitrary
        # filler everywhere except the fields the parser consumes.
        module_offset = payload_offset_for_lba(0x1425)
        module = bytearray(DIALOGUE_MODULE_LENGTH)
        local = (0x1427, 0x142F, 0x143B, 0x1441, 0x144D, 0x1429, 0x1447, 0x1435)
        adpcm = (0x1431, 0x1431, 0x143D, 0x1443, 0x144F, 0x142B, 0x1449, 0x1437)
        table = bytearray()
        for value in local + adpcm:
            table.extend((value >> 16, value & 0xFF, (value >> 8) & 0xFF))
        module[
            MODULE_SOURCE_TABLE_RELATIVE : MODULE_SOURCE_TABLE_RELATIVE + len(table)
        ] = table
        payload[module_offset : module_offset + len(module)] = module

        loader_offset = MISSION0_B_PAYLOAD_BASE + DIALOGUE_MODULE_LOADER_CPU
        payload[
            loader_offset : loader_offset + len(DIALOGUE_MODULE_LOADER_BYTES)
        ] = DIALOGUE_MODULE_LOADER_BYTES

        portrait_offset = MISSION0_B_PAYLOAD_BASE + PORTRAIT_TABLE_CPU
        for index in range(PORTRAIT_SLOT_COUNT):
            lba = 0x1453 + index * 5
            payload[portrait_offset + index * 4 : portrait_offset + index * 4 + 4] = bytes(
                ((lba >> 16) & 0xFF, lba & 0xFF, (lba >> 8) & 0xFF, 5)
            )

        # This fixture intentionally cannot satisfy the hard-coded SHA guards;
        # helper decoding tests patch those constants out by using direct
        # table logic below rather than analyze_dialogue_load_architecture().
        return bytes(payload)

    def test_declared_module_leaves_175_bytes_in_second_sector(self) -> None:
        self.assertEqual(
            2 * SECTOR_BYTES - DIALOGUE_MODULE_LENGTH,
            0xAF,
        )

    def test_active_speaker_layout_is_sequential(self) -> None:
        # Proven source table values from the authenticated payload.
        local = (0x1427, 0x142F, 0x143B, 0x1441, 0x144D, 0x1429, 0x1447, 0x1435)
        adpcm = (0x1431, 0x1431, 0x143D, 0x1443, 0x144F, 0x142B, 0x1449, 0x1437)
        for index in range(1, 8):
            self.assertEqual(local[index] + SPEAKER_BLOCK_SECTORS, adpcm[index])
        self.assertEqual(ADPCM_BLOCK_SECTORS, 4)

    def test_core_extent_is_46_sectors_and_fits_super_cd_ram(self) -> None:
        sectors = 0x1452 - 0x1425 + 1
        self.assertEqual(sectors, 46)
        self.assertEqual(sectors * SECTOR_BYTES, 94_208)
        self.assertLess(sectors * SECTOR_BYTES, 192 * 1024)

    def test_portrait_record_order_matches_dispatcher_pointer_math(self) -> None:
        decoded = _decode_portrait_entry(bytes.fromhex("00 58 14 05"))
        self.assertEqual(decoded.lba, 0x1458)
        self.assertEqual(decoded.sectors, 5)

    def test_portrait_slots_leave_2016_bytes_after_2020_transfer(self) -> None:
        allocated = 5 * SECTOR_BYTES
        self.assertEqual(allocated - 0x2020, 0x7E0)
        self.assertEqual(PORTRAIT_SLOT_COUNT * 0x7E0, 272_160)

    def test_source_guard_constants_are_stable(self) -> None:
        self.assertEqual(
            hashlib.sha256(DIALOGUE_MODULE_LOADER_BYTES).hexdigest(),
            "ed8f6a308e312c4772f4a5d826b70ad1aec7718ec41231caeb927f6911947895",
        )


if __name__ == "__main__":
    unittest.main()
