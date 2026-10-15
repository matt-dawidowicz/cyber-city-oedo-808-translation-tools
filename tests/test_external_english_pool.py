from __future__ import annotations

import unittest

from cyber_oedo.runtime.external_english_pool import (
    POOL_BANK_BYTES,
    POOL_CAPACITY,
    ExternalPoolContractError,
    decode_pool_redirect,
    inspect_native_pool_record,
    pool_address,
)


class ExternalEnglishPoolTests(unittest.TestCase):
    def _pool(self, offset: int, body: bytes) -> bytes:
        pool = bytearray(POOL_CAPACITY)
        pool[offset : offset + len(body)] = body
        return bytes(pool)

    def test_redirect_decodes_u16_little_endian_with_explicit_zero_tail(self) -> None:
        self.assertEqual(decode_pool_redirect(bytes.fromhex("27 28 7B 34 12 00")), 0x1234)
        for bad in (
            bytes.fromhex("27 28 7B 34 12"),
            bytes.fromhex("27 28 7B 34 12 01"),
            bytes.fromhex("27 28 7D 34 12 00"),
            bytes.fromhex("27 28 7B FF FF 00"),
        ):
            with self.subTest(redirect=bad.hex()):
                with self.assertRaises(ExternalPoolContractError):
                    decode_pool_redirect(bad)

    def test_bank_boundary_rollover_is_explicit(self) -> None:
        before = pool_address(POOL_BANK_BYTES - 1)
        after = pool_address(POOL_BANK_BYTES)
        self.assertEqual((before.bank, before.cpu_address), (0x7C, 0x7FFF))
        self.assertEqual((after.bank, after.cpu_address), (0x7D, 0x6000))
        self.assertEqual(pool_address(POOL_CAPACITY - 1).bank, 0x7F)
        with self.assertRaises(ExternalPoolContractError):
            pool_address(POOL_CAPACITY)

    def test_fixed_segments_cross_bank_and_preserve_control_operands(self) -> None:
        start = POOL_BANK_BYTES - 3
        body = bytes.fromhex("7D 45 80 81 7C 2A 00 3D 00 06 00")
        result = inspect_native_pool_record(self._pool(start, body), start)
        self.assertEqual(result.bank_range, (0x7C, 0x7D))
        self.assertEqual(result.fixed_segments, 1)
        self.assertEqual(result.stock_controls, (0x2A, 0x3D))
        self.assertEqual(result.consumed_bytes, len(body))

    def test_vwf_cell_tokens_and_stock_page_break(self) -> None:
        body = bytes.fromhex("7D 56 01 00 09 FF FF FF 40 7D 45 80 7C 00")
        result = inspect_native_pool_record(self._pool(1, body), 1)
        self.assertEqual((result.fixed_segments, result.vwf_segments), (1, 1))
        self.assertEqual(result.stock_controls, (0x40,))

    def test_pool_verifier_rejects_invalid_or_overlong_records(self) -> None:
        cases = (
            bytes.fromhex("7D 45 7C 00"),
            bytes.fromhex("7D 56 FF 00 00"),
            bytes.fromhex("7D 56 0A 01 FF FF 00"),
            bytes.fromhex("7D 45 80 7C 7B 00"),
            bytes.fromhex("7D 45 80 7C 7D 00"),
        )
        for case in cases:
            with self.subTest(case=case.hex()):
                with self.assertRaises(ExternalPoolContractError):
                    inspect_native_pool_record(self._pool(5, case), 5)
        with self.assertRaises(ExternalPoolContractError):
            inspect_native_pool_record(self._pool(0x7FFD, b"\x7D\x45\x80"), 0x7FFD)
        with self.assertRaises(ExternalPoolContractError):
            inspect_native_pool_record(self._pool(0, b"\x7D\x45\x80\x7C"), 0, max_bytes=4)

    def test_wrong_bank_extent_and_start_offset_are_rejected(self) -> None:
        with self.assertRaises(ExternalPoolContractError):
            inspect_native_pool_record(bytes(POOL_CAPACITY - 1), 0)
        with self.assertRaises(ExternalPoolContractError):
            inspect_native_pool_record(bytes(POOL_CAPACITY), POOL_CAPACITY)


if __name__ == "__main__":
    unittest.main()
