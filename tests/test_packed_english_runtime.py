from __future__ import annotations

import hashlib
import unittest

from cyber_oedo.runtime.packed_english_runtime import (
    BARTENDER_PROOF_ENGLISH,
    BARTENDER_PROOF_SOURCE,
    FONT_FETCH_HOOK_EXPECTED,
    MISSION0_B_PAYLOAD_BASE,
    PAIR_TABLE_CPU,
    PADDING_SPLIT_CPU,
    RUNTIME_CODE_CPU,
    RUNTIME_REGION_END_CPU,
    RUNTIME_REGION_SHA256,
    PackedRuntimeError,
    build_bartender_proof,
    build_runtime,
    compact_repertoire_for_texts,
    encode_fixed_footprint,
    validate_proof_against_payload,
    validate_runtime_region,
)
from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas
from cyber_oedo.text.packed_english import PackedEnglishDictionary


def synthetic_atlas(characters: str) -> RasterizedAtlas:
    glyphs = tuple(
        bytes(((glyph_id + row) & 0xFF for row in range(16)))
        for glyph_id in range(len(characters))
    )
    return RasterizedAtlas(
        characters=characters,
        glyphs=glyphs,
        source_sha256="00" * 32,
        config=RasterConfig(),
    )


class PackedEnglishRuntimeTests(unittest.TestCase):
    def _dictionary_and_atlas(
        self,
        texts: tuple[str, ...] = (BARTENDER_PROOF_ENGLISH,),
    ) -> tuple[PackedEnglishDictionary, RasterizedAtlas]:
        repertoire = compact_repertoire_for_texts(texts)
        dictionary = PackedEnglishDictionary.from_texts(
            texts,
            repertoire=repertoire,
        )
        return dictionary, synthetic_atlas(repertoire.characters)

    def test_authenticated_padding_contract_matches_documented_hash(self) -> None:
        region = (
            b"\x00" * (PADDING_SPLIT_CPU - RUNTIME_CODE_CPU)
            + b"\xE5" * (RUNTIME_REGION_END_CPU - PADDING_SPLIT_CPU)
        )
        self.assertEqual(
            hashlib.sha256(region).hexdigest(),
            RUNTIME_REGION_SHA256,
        )

        payload = bytearray(
            MISSION0_B_PAYLOAD_BASE + RUNTIME_REGION_END_CPU
        )
        start = MISSION0_B_PAYLOAD_BASE + RUNTIME_CODE_CPU
        payload[start : start + len(region)] = region
        self.assertTrue(validate_runtime_region(bytes(payload)))
        payload[start + 17] ^= 1
        self.assertFalse(validate_runtime_region(bytes(payload)))

    def test_runtime_fits_guarded_mission0_region(self) -> None:
        dictionary, atlas = self._dictionary_and_atlas(
            (
                BARTENDER_PROOF_ENGLISH,
                "Sengoku: Where are we?",
                "Benten: Move.",
            )
        )
        runtime = build_runtime(dictionary, atlas)
        self.assertLess(runtime.code_end_cpu, PAIR_TABLE_CPU)
        self.assertLess(runtime.pair_table_end_cpu, runtime.atlas_cpu)
        self.assertLessEqual(runtime.atlas_end_cpu, RUNTIME_REGION_END_CPU)
        self.assertEqual(runtime.labels["glyph_hook"], RUNTIME_CODE_CPU)
        self.assertIn(bytes.fromhex("20 60 E0"), runtime.code)

    def test_fixed_footprint_uses_private_tokens_and_stock_ignored_padding(self) -> None:
        dictionary, _ = self._dictionary_and_atlas()
        encoded = encode_fixed_footprint(
            dictionary,
            BARTENDER_PROOF_ENGLISH,
            len(BARTENDER_PROOF_SOURCE),
        )
        visible_bytes = len(dictionary.encode_visible_text(BARTENDER_PROOF_ENGLISH))
        self.assertEqual(len(encoded), len(BARTENDER_PROOF_SOURCE))
        for offset in range(0, visible_bytes, 2):
            self.assertGreaterEqual(encoded[offset], 0xF0)
            self.assertLessEqual(encoded[offset], 0xFC)
        self.assertEqual(
            encoded[visible_bytes:],
            b"\x80" * (len(BARTENDER_PROOF_SOURCE) - visible_bytes),
        )

    def test_bartender_proof_contains_only_one_text_patch_plus_runtime(self) -> None:
        dictionary, atlas = self._dictionary_and_atlas()
        proof = build_bartender_proof(dictionary, atlas)
        self.assertEqual(len(proof.patches), 5)
        self.assertEqual(proof.patches[0].expected, FONT_FETCH_HOOK_EXPECTED)
        self.assertEqual(proof.patches[-1].expected, BARTENDER_PROOF_SOURCE)
        self.assertEqual(proof.english, BARTENDER_PROOF_ENGLISH)

    def test_proof_validates_against_synthetic_guarded_payload(self) -> None:
        dictionary, atlas = self._dictionary_and_atlas()
        proof = build_bartender_proof(dictionary, atlas)
        end = max(patch.end_offset for patch in proof.patches)
        payload = bytearray(end)

        # Populate the complete authenticated runtime padding region.
        runtime_start = MISSION0_B_PAYLOAD_BASE + RUNTIME_CODE_CPU
        runtime_region = (
            b"\x00" * (PADDING_SPLIT_CPU - RUNTIME_CODE_CPU)
            + b"\xE5" * (RUNTIME_REGION_END_CPU - PADDING_SPLIT_CPU)
        )
        payload[runtime_start : runtime_start + len(runtime_region)] = runtime_region

        for patch in (proof.patches[0], proof.patches[-1]):
            payload[patch.offset : patch.end_offset] = patch.expected

        rows = validate_proof_against_payload(bytes(payload), proof)
        self.assertTrue(all(row["matched"] for row in rows))

    def test_mismatched_atlas_order_is_rejected(self) -> None:
        dictionary, atlas = self._dictionary_and_atlas()
        reversed_atlas = RasterizedAtlas(
            characters=atlas.characters[::-1],
            glyphs=atlas.glyphs[::-1],
            source_sha256=atlas.source_sha256,
            config=atlas.config,
        )
        with self.assertRaisesRegex(PackedRuntimeError, "exactly match"):
            build_runtime(dictionary, reversed_atlas)


if __name__ == "__main__":
    unittest.main()
