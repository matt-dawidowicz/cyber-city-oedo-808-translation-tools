"""Fail-closed structural tests: CD sidecar through MPR6 (non-release)."""
import unittest

from cyber_oedo.runtime.adpcm_cd_sidecar_mpr6_candidate import (
    build_mpr6_stub, build_mpr6_sector, build_mpr6_adpcm_cache,
    build_unverified_mpr6_cd_sidecar,
)

STOCK_COMMAND = bytes.fromhex(
    "20 42 e0 20 1a 86 aa d0 fa ad dd 8f f0 29 0a 18 "
    "6d dd 8f aa bd 8b 8b 85 fc bd 8c 8b 85 fe bd 8d "
    "8b 85 fd a9 04 85 f8 64 ff a9 00 85 fa a9 e0 "
    "85 fb 20 33 e0 aa d0 c9 60"
)


class Mpr6CdSidecarTests(unittest.TestCase):
    def test_mpr3_not_remapped(self):
        stub = build_mpr6_stub()
        self.assertEqual(len(stub), 56)
        self.assertIn(
            bytes.fromhex("43 40 48 A9 75 53 40 20 00 C0 68 53 40 60"),
            stub,
        )
        self.assertNotIn(bytes.fromhex("53 08"), stub)
        self.assertIn(bytes.fromhex("20 09 E0"), stub)

    def test_sidecar_separates_code_and_cache_tags(self):
        cache = build_mpr6_adpcm_cache()
        self.assertEqual(len(cache), 85)
        self.assertEqual(cache[:7], bytes.fromhex("43 20 48 A9 6B 53 20"))
        self.assertIn(bytes.fromhex("AD 00 C8 CD DD 8F"), cache)
        self.assertIn(bytes.fromhex("8D 01 C8"), cache)
        self.assertNotIn(bytes.fromhex("53 40"), cache)
        sector = build_mpr6_sector(STOCK_COMMAND)
        self.assertEqual(len(sector), 2048)
        self.assertEqual(sector[0x31:0x34], bytes.fromhex("20 38 C0"))
        self.assertEqual(sector[56:141], cache)
        self.assertEqual(sector[141:], bytes(2048-141))

    def test_refuses_unverified_source_and_implicit_optin(self):
        with self.assertRaisesRegex(ValueError, "unsafe research"):
            build_unverified_mpr6_cd_sidecar(b"not source")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            build_unverified_mpr6_cd_sidecar(
                b"not source", acknowledge_unsafe_research=True
            )
        with self.assertRaisesRegex(ValueError, "mismatch"):
            build_mpr6_sector(bytes(56))


if __name__ == "__main__":
    unittest.main()
