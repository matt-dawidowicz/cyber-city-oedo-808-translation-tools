from __future__ import annotations

import unittest

from cyber_oedo.runtime.card_ram_adpcm_cache import (
    ADPCM_CACHE_CAVE_CPU,
    ADPCM_CACHE_CAVE_EXPECTED,
    ADPCM_CACHE_CAVE_REPLACEMENT,
    ADPCM_CALL_EXPECTED,
    ADPCM_CALL_REPLACEMENT,
    build_speaker_adpcm_cache_benchmark,
)


class CardRamAdpcmCacheTests(unittest.TestCase):
    def test_hook_replaces_only_ad_trans_call(self) -> None:
        self.assertEqual(ADPCM_CALL_EXPECTED, bytes.fromhex("20 33 E0"))
        self.assertEqual(
            ADPCM_CALL_REPLACEMENT,
            bytes((0x20, ADPCM_CACHE_CAVE_CPU & 0xFF, ADPCM_CACHE_CAVE_CPU >> 8)),
        )

    def test_cave_fits_remaining_authenticated_zero_run(self) -> None:
        self.assertEqual(len(ADPCM_CACHE_CAVE_REPLACEMENT), 95)
        self.assertEqual(ADPCM_CACHE_CAVE_EXPECTED, bytes(95))
        self.assertLessEqual(ADPCM_CACHE_CAVE_CPU + len(ADPCM_CACHE_CAVE_REPLACEMENT), 0x4D6C)

    def test_cave_uses_local_cd_read_then_ad_write(self) -> None:
        code = ADPCM_CACHE_CAVE_REPLACEMENT
        self.assertIn(bytes.fromhex("20 09 E0"), code)
        self.assertIn(bytes.fromhex("20 39 E0"), code)
        self.assertIn(bytes.fromhex("A9 6B 53 20 A9 6C 53 40"), code)

    def test_benchmark_remains_source_guarded(self) -> None:
        benchmark = build_speaker_adpcm_cache_benchmark()
        self.assertEqual(len(benchmark.patches), 2)
        self.assertGreater(benchmark.changed_bytes, 0)


if __name__ == "__main__":
    unittest.main()
