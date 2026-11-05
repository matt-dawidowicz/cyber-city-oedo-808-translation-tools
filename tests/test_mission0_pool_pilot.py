from __future__ import annotations

import unittest
import hashlib
from unittest.mock import patch

from cyber_oedo.runtime.mission0_pool_pilot import (
    BARTENDER_MARKER_OFFSET,
    BARTENDER_SOURCE_TEXT,
    DIAGNOSTIC_INTRO_MARKER_OFFSET,
    DIAGNOSTIC_INTRO_TERMINATOR_OFFSET,
    DEFAULT_PILOT_TEXT,
    M0B_POOL_LAYOUT,
    M0B_SOURCE_BASE,
    M0B_TABLE_LOADER_CPU,
    M0B_TABLE_LOADER_EXPECTED,
    M0B_TABLE_LOADER_REPLACEMENT,
    POOL_START_RELATIVE_SECTOR,
    SOURCE_REDIRECT_BYTES,
    _make_runtime,
    build_m0b_pilot_patches,
    build_m0b_intro_diagnostic_patch,
    render_pilot_mesen_trace,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas


class SourceCodeView:
    """A read-only virtual original holding exactly the expected source bytes."""

    def __init__(self, font_length: int, code_length: int) -> None:
        base = M0B_SOURCE_BASE
        text = BARTENDER_SOURCE_TEXT.encode("shift_jis")
        self.slices = {
            (base + M0B_TABLE_LOADER_CPU, 8): M0B_TABLE_LOADER_EXPECTED,
            (base + 0x9543, 3): bytes.fromhex("20 11 9F"),
            (base + 0x95D4, 3): bytes.fromhex("C9 80 F0"),
            (base + 0x9F11, 3): bytes.fromhex("B2 7F 60"),
            (base + 0x9F14, 6): bytes.fromhex("E6 7F D0 02 E6 80"),
            (base + 0x56C0, 3): bytes.fromhex("20 60 E0"),
            (base + 0xA400, font_length):
                bytes(min(font_length, 0x400))
                + bytes((0xE5,)) * max(font_length - 0x400, 0),
            (base + 0xAC00, code_length): bytes((0xE5,)) * code_length,
            (POOL_START_RELATIVE_SECTOR * 2048, 0x8000): bytes(0x8000),
            (BARTENDER_MARKER_OFFSET + 2, SOURCE_REDIRECT_BYTES):
                text[:SOURCE_REDIRECT_BYTES],
        }

    def __getitem__(self, key: slice) -> bytes:
        if not isinstance(key, slice) or key.step is not None:
            raise ValueError("only guarded source slices are accepted")
        try:
            return self.slices[(key.start, key.stop - key.start)]
        except KeyError as error:
            raise ValueError("unproved source byte slice") from error


class Mission0PoolPilotTests(unittest.TestCase):
    def _fixture(self) -> tuple[EnglishGlyphTable, RasterizedAtlas]:
        repertoire = " ?Bartend:Wlcom."
        glyphs = EnglishGlyphTable(repertoire)
        atlas = RasterizedAtlas(
            characters=repertoire,
            glyphs=tuple(bytes((i + n) % 256 for n in range(16))
                         for i in range(len(repertoire))),
            source_sha256="0" * 64,
            config=RasterConfig(),
        )
        return glyphs, atlas

    def test_indexed_loader_size_change_is_proven_explicit(self) -> None:
        self.assertEqual(
            M0B_TABLE_LOADER_EXPECTED.hex(), "a9018506a9038507"
        )
        self.assertEqual(
            M0B_TABLE_LOADER_REPLACEMENT.hex(), "a9008506a91c8507"
        )
        self.assertEqual(M0B_POOL_LAYOUT.code_cpu, 0xB000)
        self.assertEqual(M0B_POOL_LAYOUT.font_regions[0].cpu_address, 0xA800)

    def test_native_runtime_and_pool_helper_fit_verified_load_footprint(self) -> None:
        glyphs, atlas = self._fixture()
        runtime = _make_runtime(glyphs, atlas)
        code_start = M0B_POOL_LAYOUT.code_cpu
        code_end = code_start + len(runtime.full_code)
        font_end = 0xA800 + len(runtime.font)
        self.assertLess(code_end, 0xC000)
        self.assertLessEqual(font_end, code_start)
        for label in (
            "pool_dispatch", "pool_parser_entry", "pool_redirect",
            "restore_source", "pool_read", "pool_advance", "pool_load",
            "pool_load_loop", "load_error", "saved_cd_args",
        ):
            self.assertIn(label, runtime.labels)
        self.assertLess(runtime.labels["pool_dispatch"], 0xC000)

    def test_pilot_modifications_are_separate_and_preserve_original_end(self) -> None:
        glyphs, atlas = self._fixture()
        runtime = _make_runtime(glyphs, atlas)
        sparse = SourceCodeView(len(runtime.font), len(runtime.full_code))
        with patch(
            "cyber_oedo.runtime.mission0_pool_pilot._verify_original"
        ):
            patches = build_m0b_pilot_patches(
                sparse, glyphs, atlas, english=DEFAULT_PILOT_TEXT
            )
        self.assertEqual(len(patches), 10)
        by_label = {item.label: item for item in patches}
        loader = next(item for item in patches if "indexed table" in item.label)
        self.assertEqual(loader.replacement, M0B_TABLE_LOADER_REPLACEMENT)
        code = next(item for item in patches if "installed at CPU B000" in item.label)
        self.assertEqual(code.offset, M0B_SOURCE_BASE + 0xAC00)
        self.assertEqual(code.replacement[:len(runtime.native_code)], runtime.native_code)
        source = next(item for item in patches if "bartender dialogue" in item.label)
        self.assertEqual(source.offset, BARTENDER_MARKER_OFFSET + 2)
        self.assertEqual(source.replacement[:3], bytes.fromhex("7B 00 00"))
        self.assertEqual(
            int.from_bytes(source.replacement[3:5], "little"),
            len(BARTENDER_SOURCE_TEXT.encode("shift_jis")) - 5,
        )
        self.assertNotIn(b"\x00", source.replacement[3:4])
        pool = next(item for item in patches if "16 tail sectors" in item.label)
        self.assertEqual(pool.replacement[:2], bytes.fromhex("7D 45"))
        self.assertEqual(len(pool.replacement), 0x8000)

    def test_mesen_trace_uses_actual_compiled_labels_and_is_read_only(self) -> None:
        glyphs, atlas = self._fixture()
        runtime = _make_runtime(glyphs, atlas)
        lua = render_pilot_mesen_trace(runtime.labels)
        self.assertIn(f"on_pc(0x{runtime.labels['pool_read']:04X}", lua)
        self.assertIn(f"on_pc(0x{runtime.labels['pool_load']:04X}", lua)
        self.assertIn("EMULATOR_CERTIFIED=false", lua)
        self.assertNotIn("emu.write(", lua)
        self.assertNotIn("__POOL_", lua)
        self.assertNotIn("__DISPATCH__", lua)
        with self.assertRaisesRegex(ValueError, "missing/out-of-range"):
            render_pilot_mesen_trace({"pool_dispatch": 0x1000})

    def test_source_guarded_diagnostic_intro_preserves_original_terminator(self) -> None:
        start = DIAGNOSTIC_INTRO_MARKER_OFFSET
        stop = DIAGNOSTIC_INTRO_TERMINATOR_OFFSET
        record = (
            bytes.fromhex("27 28 81 75 89 B4 82")
            + bytes((0x82,)) * (stop - start - 7)
            + bytes((0,))
        )
        payload = bytearray(stop + 1)
        payload[start:stop + 1] = record
        with patch(
            "cyber_oedo.runtime.mission0_pool_pilot.DIAGNOSTIC_INTRO_RECORD_SHA256",
            hashlib.sha256(record).hexdigest(),
        ):
            result = build_m0b_intro_diagnostic_patch(bytes(payload))
            self.assertEqual(result.offset, start + 2)
            self.assertEqual(result.replacement, bytes.fromhex("7B 00 00 B0 02"))
            skip = int.from_bytes(result.replacement[3:5], "little")
            self.assertEqual(result.offset + len(result.replacement) + skip, stop)
            self.assertEqual(payload[stop], 0)
            self.assertIn("DIAGNOSTIC-ONLY", result.label)
            payload[start + 2] ^= 1
            with self.assertRaisesRegex(ValueError, "authenticated bytes"):
                build_m0b_intro_diagnostic_patch(bytes(payload))

    def test_diagnostic_intro_requires_explicit_opt_in(self) -> None:
        # All standard builder tests still generate exactly ten source patches.
        import inspect

        from cyber_oedo.runtime.mission0_pool_pilot import (
            build_m0b_pilot_disc,
            build_m0b_pilot_patches,
        )

        self.assertIs(
            inspect.signature(build_m0b_pilot_patches)
            .parameters["diagnostic_intro_redirect"].default, False
        )
        self.assertIs(
            inspect.signature(build_m0b_pilot_disc)
            .parameters["diagnostic_intro_redirect"].default, False
        )

    def test_missing_original_bytes_are_refused(self) -> None:
        glyphs, atlas = self._fixture()
        runtime = _make_runtime(glyphs, atlas)
        sparse = SourceCodeView(len(runtime.font), len(runtime.full_code))
        sparse.slices[(M0B_SOURCE_BASE + 0x9543, 3)] = b"\xFF\xFF\xFF"
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            with self.assertRaisesRegex(ValueError, "source signature mismatch"):
                build_m0b_pilot_patches(sparse, glyphs, atlas)

    def test_pilot_rejects_unwrapped_or_unsupported_english(self) -> None:
        glyphs, atlas = self._fixture()
        runtime = _make_runtime(glyphs, atlas)
        sparse = SourceCodeView(len(runtime.font), len(runtime.full_code))
        with patch("cyber_oedo.runtime.mission0_pool_pilot._verify_original"):
            with self.assertRaisesRegex(ValueError, "one 22-column"):
                build_m0b_pilot_patches(
                    sparse, glyphs, atlas,
                    english="This sentence is deliberately far too long for one line.",
                )


if __name__ == "__main__":
    unittest.main()
