from __future__ import annotations

import unittest

from cyber_oedo.runtime.cd_load_optimization import (
    PackBitsError,
    packbits_words,
    unpackbits_words,
)


class WordPackBitsTests(unittest.TestCase):
    def test_round_trip_mixed_words(self) -> None:
        source = (
            b"AB" * 12
            + b"CD" + b"EF" + b"GH"
            + b"IJ" * 3
            + bytes(range(32))
        )
        encoded = packbits_words(source)
        self.assertEqual(unpackbits_words(encoded, len(source)), source)

    def test_long_repeat_is_split_at_128_words(self) -> None:
        source = b"XY" * 300
        encoded = packbits_words(source)
        self.assertEqual(unpackbits_words(encoded, len(source)), source)
        self.assertLess(len(encoded), 20)

    def test_odd_source_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackBitsError, "even"):
            packbits_words(b"abc")

    def test_reserved_control_is_rejected(self) -> None:
        with self.assertRaisesRegex(PackBitsError, "reserved"):
            unpackbits_words(bytes((128,)))


if __name__ == "__main__":
    unittest.main()
