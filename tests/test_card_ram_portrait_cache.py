from __future__ import annotations

import unittest

from cyber_oedo.runtime.card_ram_portrait_cache import (
    PORTRAIT_CACHE_CAVE_CPU,
    PORTRAIT_CACHE_CAVE_EXPECTED,
    PORTRAIT_CACHE_CAVE_REPLACEMENT,
    PORTRAIT_CD_READ_EXPECTED,
    PORTRAIT_CD_READ_REPLACEMENT,
    PORTRAIT_TAG_ADDRESS,
    build_portrait_cache_benchmark,
)


class CardRamPortraitCacheTests(unittest.TestCase):
    def test_hook_redirects_only_stock_cd_read_call(self) -> None:
        self.assertEqual(PORTRAIT_CD_READ_EXPECTED, bytes.fromhex("20 09 E0"))
        self.assertEqual(
            PORTRAIT_CD_READ_REPLACEMENT,
            bytes((0x20, PORTRAIT_CACHE_CAVE_CPU & 0xFF, PORTRAIT_CACHE_CAVE_CPU >> 8)),
        )

    def test_cave_fits_authenticated_zero_run(self) -> None:
        self.assertEqual(len(PORTRAIT_CACHE_CAVE_REPLACEMENT), 103)
        self.assertEqual(PORTRAIT_CACHE_CAVE_EXPECTED, bytes(103))
        self.assertLess(PORTRAIT_CACHE_CAVE_CPU + len(PORTRAIT_CACHE_CAVE_REPLACEMENT), 0x4D6C)

    def test_cave_contains_real_cd_read_and_tia(self) -> None:
        code = PORTRAIT_CACHE_CAVE_REPLACEMENT
        self.assertIn(bytes.fromhex("20 09 E0"), code)
        self.assertIn(bytes.fromhex("E3 00 A0 02 00 20 20"), code)
        self.assertIn(bytes.fromhex("A9 68 53 20 A9 69 53 40"), code)

    def test_cache_tag_is_beyond_five_sector_fill(self) -> None:
        # $A000 + 5 * $800 = $C800; the tag begins exactly after the fill.
        self.assertEqual(PORTRAIT_TAG_ADDRESS, 0xA000 + 5 * 0x800)

    def test_benchmark_remains_source_guarded(self) -> None:
        benchmark = build_portrait_cache_benchmark()
        self.assertEqual(len(benchmark.patches), 2)
        self.assertGreater(benchmark.changed_bytes, 0)


if __name__ == "__main__":
    unittest.main()
