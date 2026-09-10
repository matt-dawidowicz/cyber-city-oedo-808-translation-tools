"""Regression tests for binary coordinates and PC Engine graphics."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from cyber_oedo.analysis.disassemble_huc6280 import (
    OPCODES,
    decode_instruction,
    linear_disassemble,
)
from cyber_oedo.disc.cdrom_mode1 import (
    MODE1_SYNC,
    mode1_integrity_matches,
    read_payload_range,
    rebuild_mode1_sector,
    PayloadPatch,
)
from cyber_oedo.disc.extract_track2_mode1 import extract_mode1_payload
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.disc.game_layout import (
    MODE1_USER_DATA_OFFSET,
    RAW_SECTOR_SIZE,
    SECTOR_SIZE,
    absolute_lba,
    bank_for_offset,
    payload_offset,
)
from cyber_oedo.graphics.pce_graphics import decode_tile, encode_tile


def synthetic_mode1_sector(payload: bytes) -> bytes:
    """Return one structurally valid synthetic Mode 1 sector."""

    if len(payload) != SECTOR_SIZE:
        raise ValueError("synthetic payload must contain 2048 bytes")
    raw = bytearray(RAW_SECTOR_SIZE)
    raw[: len(MODE1_SYNC)] = MODE1_SYNC
    raw[15] = 1
    raw[MODE1_USER_DATA_OFFSET : MODE1_USER_DATA_OFFSET + SECTOR_SIZE] = payload
    return rebuild_mode1_sector(raw)


class GameLayoutTests(unittest.TestCase):
    """Protect payload/disc coordinate invariants."""

    def test_bank_boundaries_are_half_open(self) -> None:
        """Assign boundary bytes to exactly one mission bank."""

        self.assertEqual(bank_for_offset(0), "MISSION_0")
        self.assertEqual(bank_for_offset(5376 * SECTOR_SIZE - 1), "MISSION_0")
        self.assertEqual(bank_for_offset(5376 * SECTOR_SIZE), "MISSION_1")

    def test_coordinate_helpers_are_stable(self) -> None:
        """Convert payload and absolute-disc coordinates deterministically."""

        self.assertEqual(payload_offset(3, 0x123), 3 * SECTOR_SIZE + 0x123)
        self.assertEqual(absolute_lba(0), 3590)
        self.assertEqual(absolute_lba(100), 3690)


class TileCodecTests(unittest.TestCase):
    """Protect the PC Engine four-plane tile codec."""

    def test_tile_codec_round_trips_palette_indexes(self) -> None:
        """Encode and decode every four-bit plane without loss."""

        pixels = [(index * 7) % 16 for index in range(64)]
        encoded = encode_tile(pixels)
        self.assertEqual(len(encoded), 32)
        self.assertEqual(decode_tile(encoded), pixels)

    def test_tile_encoder_rejects_invalid_pixels(self) -> None:
        """Reject malformed tile dimensions and palette values."""

        with self.assertRaises(ValueError):
            encode_tile([0] * 63)
        with self.assertRaises(ValueError):
            encode_tile([0] * 63 + [16])


class Mode1Tests(unittest.TestCase):
    """Protect raw Mode 1 extraction and patch integrity."""

    def test_extractor_returns_exact_user_data(self) -> None:
        """Extract exactly one synthetic 2048-byte payload."""

        payload = bytes(index % 251 for index in range(SECTOR_SIZE))
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            image = root / "synthetic.img"
            output = root / "payload.bin"
            image.write_bytes(synthetic_mode1_sector(payload))
            written, digest = extract_mode1_payload(
                image,
                output,
                start_lba=0,
                sector_count=1,
            )
            self.assertEqual(written, SECTOR_SIZE)
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(len(digest), 64)

    def test_cross_sector_patch_rebuilds_both_sectors(self) -> None:
        """Keep EDC/ECC valid across a payload-sector boundary edit."""

        first = bytes(index % 251 for index in range(SECTOR_SIZE))
        second = bytes((index + 31) % 251 for index in range(SECTOR_SIZE))
        patch = PayloadPatch(
            offset=SECTOR_SIZE - 8,
            expected=first[-8:] + second[:8],
            replacement=b"Z" * 16,
            label="cross-sector test",
        )
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "synthetic.img"
            image.write_bytes(
                synthetic_mode1_sector(first) + synthetic_mode1_sector(second)
            )
            reports = apply_payload_patches(
                image,
                (patch,),
                start_lba=0,
                sector_count=2,
            )
            raw = image.read_bytes()
        self.assertEqual([report.relative_sector for report in reports], [0, 1])
        self.assertTrue(mode1_integrity_matches(raw[:RAW_SECTOR_SIZE]))
        self.assertTrue(mode1_integrity_matches(raw[RAW_SECTOR_SIZE:]))

    def test_payload_reader_joins_sector_data(self) -> None:
        """Read a bounded range across adjacent raw sectors."""

        first = bytes(index % 251 for index in range(SECTOR_SIZE))
        second = bytes((index + 17) % 251 for index in range(SECTOR_SIZE))
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / "synthetic.img"
            image.write_bytes(
                synthetic_mode1_sector(first) + synthetic_mode1_sector(second)
            )
            actual = read_payload_range(
                image,
                SECTOR_SIZE - 5,
                12,
                start_lba=0,
                sector_count=2,
            )
        self.assertEqual(actual, first[-5:] + second[:7])


class DisassemblerTests(unittest.TestCase):
    """Protect deterministic HuC6280 diagnostic decoding."""

    def test_opcode_table_is_complete(self) -> None:
        """Keep all 256 opcode entries available."""

        self.assertEqual(len(OPCODES), 256)
        self.assertEqual(OPCODES[0x20], ("jsr", "abs"))
        self.assertEqual(OPCODES[0x73], ("tii", "blk"))
        self.assertEqual(OPCODES[0xF4], ("set", "imp"))

    def test_call_and_branch_targets_are_formatted(self) -> None:
        """Resolve absolute and signed-relative operands."""

        call = decode_instruction(
            bytes.fromhex("20 60 E0"),
            0,
            0x00136589,
            0x4D89,
        )
        branch = decode_instruction(
            bytes.fromhex("80 EA"),
            0,
            0x00072EDF,
            0x66DF,
        )
        self.assertEqual(call.operand, "$E060")
        self.assertEqual(branch.operand, "$66CB")

    def test_linear_disassembly_retains_both_coordinates(self) -> None:
        """Advance payload and logical CPU addresses together."""

        instructions = list(
            linear_disassemble(
                bytes.fromhex("A9 0B 60"),
                0x00137165,
                0x5965,
            )
        )
        self.assertEqual(
            [
                (item.payload_offset, item.cpu_address, item.mnemonic)
                for item in instructions
            ],
            [
                (0x00137165, 0x5965, "lda"),
                (0x00137167, 0x5967, "rts"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
