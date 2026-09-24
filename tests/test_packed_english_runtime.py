from __future__ import annotations

import unittest

from cyber_oedo.runtime.packed_english_runtime import (
    BARTENDER_PROOF_ENGLISH,
    BARTENDER_PROOF_SOURCE,
    EXTENDED_INDEXED_TABLE_LOAD_BYTES,
    FONT_FETCH_HOOK_EXPECTED,
    INDEXED_TABLE_LENGTH_EXPECTED,
    PAIR_TABLE_CPU,
    RUNTIME_CODE_CPU,
    RUNTIME_REGION_END_CPU,
    PackedRuntimeError,
    build_bartender_proof,
    build_runtime,
    compact_repertoire_for_texts,
    encode_fixed_footprint,
    runtime_source_offset,
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

    def test_runtime_source_is_explicitly_inside_extended_indexed_load(self) -> None:
        from cyber_oedo.runtime.dialogue_interpreter import indexed_table_source_offset

        source = indexed_table_source_offset()
        self.assertEqual(runtime_source_offset(0xA800), source + 0x400)
        self.assertEqual(runtime_source_offset(0xBFFF), source + 0x1BFF)
        self.assertEqual(EXTENDED_INDEXED_TABLE_LOAD_BYTES, 0x1C00)

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
        self.assertEqual(len(proof.patches), 6)
        self.assertEqual(proof.patches[0].expected, INDEXED_TABLE_LENGTH_EXPECTED)
        self.assertEqual(proof.patches[1].expected, FONT_FETCH_HOOK_EXPECTED)
        self.assertEqual(proof.patches[-1].expected, BARTENDER_PROOF_SOURCE)
        self.assertEqual(proof.english, BARTENDER_PROOF_ENGLISH)

    def test_complete_source_interval_gate_cannot_be_bypassed(self) -> None:
        dictionary, atlas = self._dictionary_and_atlas()
        proof = build_bartender_proof(dictionary, atlas)
        end = max(patch.end_offset for patch in proof.patches)
        payload = bytearray(end)

        # Make every individual patch source match while deliberately leaving
        # the rest of the extended indexed-table source interval synthetic.
        for patch in proof.patches:
            payload[patch.offset : patch.end_offset] = patch.expected

        rows = validate_proof_against_payload(bytes(payload), proof)
        self.assertFalse(rows[0]["matched"])
        self.assertTrue(all(row["matched"] for row in rows[1:]))
        self.assertFalse(validate_runtime_region(bytes(payload)))

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
