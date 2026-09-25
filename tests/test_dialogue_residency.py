from __future__ import annotations

import unittest

from cyber_oedo.runtime.dialogue_residency import (
    EXPECTED_ALL_RESIDENT_CHECKS,
    EXPECTED_STANDARD_LOADERS,
    MODULE_BSS_BYTES,
    MODULE_CPU_END_EXCLUSIVE,
    MODULE_IMMUTABLE_SHA256,
    MODULE_MUTABLE_CPU_BYTES,
    SELF_MOD_WRITE_SITES,
    SPEAKER_LOCAL_BYTES,
    STANDARD_RESIDENT_LOADER_PREFIX,
    _decode_standard_loader,
)


class DialogueResidencyTests(unittest.TestCase):
    def test_bank_85_layout_exactly_fills_one_8k_window(self) -> None:
        module_bytes = MODULE_CPU_END_EXCLUSIVE - 0x8000
        self.assertEqual(MODULE_BSS_BYTES, 0xAF)
        self.assertEqual(SPEAKER_LOCAL_BYTES, 0x1000)
        self.assertEqual(module_bytes + MODULE_BSS_BYTES + SPEAKER_LOCAL_BYTES, 0x2000)

    def test_only_two_source_loaded_bytes_are_declared_mutable(self) -> None:
        self.assertEqual(MODULE_MUTABLE_CPU_BYTES, (0x8617, 0x8618))
        self.assertEqual(len(SELF_MOD_WRITE_SITES), 24)
        self.assertEqual(
            {target for _cpu, _opcode, target in SELF_MOD_WRITE_SITES},
            {0x8617, 0x8618},
        )

    def test_immutable_digest_constant_is_stable(self) -> None:
        self.assertEqual(
            MODULE_IMMUTABLE_SHA256,
            "c0b71dfb04f32db00dac4c7e1de7372c14173884c7dfd3970c439609da5360f1",
        )

    def test_standard_loader_decoder(self) -> None:
        blob = bytearray(STANDARD_RESIDENT_LOADER_PREFIX)
        blob.extend(
            bytes.fromhex(
                "A9 25 85 04 A9 14 85 05 A9 51 85 06 A9 0F 85 07 "
                "20 A0 6E 68"
            )
        )
        loader = _decode_standard_loader(bytes(blob), 0)
        self.assertEqual(loader.lba, 0x1425)
        self.assertEqual(loader.byte_length, 0x0F51)
        self.assertEqual(loader.loader_entry, 0x6EA0)
        self.assertEqual(loader.sectors_touched, 2)

    def test_expected_gamewide_copy_counts_are_explicit(self) -> None:
        self.assertEqual(EXPECTED_STANDARD_LOADERS, 11)
        self.assertEqual(EXPECTED_ALL_RESIDENT_CHECKS, 12)


if __name__ == "__main__":
    unittest.main()
