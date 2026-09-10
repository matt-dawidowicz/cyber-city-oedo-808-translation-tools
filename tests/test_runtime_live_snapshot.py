"""Test bank-aware validation of frozen Mission 0 ``3D`` snapshots."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

from cyber_oedo.runtime.live_snapshot import (
    LiveSnapshot,
    format_physical,
    load_snapshot,
    logical_to_physical,
    prove_three_d_snapshot,
    stream_pointer_from_memory,
)


def _snapshot(*, state: int = 0) -> LiveSnapshot:
    """Build one synthetic validated Mission 0 debugger snapshot."""

    memory = bytearray(0x10000)
    memory[0x207F:0x2081] = bytes((0x00, 0xC0))
    memory[0xC000:0xC002] = bytes((0x00, 0x06))
    record = 0xA4A0
    primary = "魔矢".encode("shift_jis")
    alternate_text = "女".encode("shift_jis")
    memory[record:record + len(primary)] = primary
    alternate = record + 0x0D
    memory[alternate:alternate + len(alternate_text)] = alternate_text
    memory[record + 0x1A] = state
    return LiveSnapshot(
        pc=0x9593,
        a=0x3D,
        mprs=(0xFF, 0xF8, 0x00, 0x81, 0x82, 0x83, 0x84, 0x00),
        memory=bytes(memory),
    )


class RuntimeLiveSnapshotTests(unittest.TestCase):
    """Verify bank, stream, record, state, and metadata validation."""

    def test_logical_to_physical_uses_correct_mpr_window(self) -> None:
        """Resolve logical addresses through the correct MPR slot."""

        snapshot = _snapshot()
        self.assertEqual(
            logical_to_physical(0x9593, snapshot.mprs),
            (0x82, 0x1593),
        )
        self.assertEqual(
            format_physical(0x9593, snapshot.mprs),
            "*82:1593",
        )
        self.assertEqual(
            format_physical(0xC000, snapshot.mprs),
            "*84:0000",
        )

    def test_direct_page_stream_pointer_uses_2000_window(self) -> None:
        """Read HuC6280 direct-page bytes from the logical $2000 window."""

        self.assertEqual(
            stream_pointer_from_memory(_snapshot().memory),
            0xC000,
        )

    def test_zero_state_selects_alternate_record_text(self) -> None:
        """Select the alternate record field when byte $1A is zero."""

        report = prove_three_d_snapshot(_snapshot(state=0))
        self.assertTrue(report["validated"])
        self.assertEqual(
            report["memory_sha256"],
            hashlib.sha256(_snapshot(state=0).memory).hexdigest(),
        )
        self.assertEqual(report["operands"]["arg0"], "0x00")
        self.assertEqual(report["operands"]["arg1"], "0x06")
        self.assertEqual(report["record"]["address"], "0xA4A0")
        self.assertEqual(report["record"]["state_address"], "0xA4BA")
        self.assertEqual(report["record"]["primary_text"], "魔矢")
        self.assertEqual(report["record"]["alternate_text"], "女")
        self.assertEqual(report["record"]["selected_offset"], "0x0D")
        self.assertEqual(report["record"]["selected_text"], "女")

    def test_nonzero_state_selects_primary_record_text(self) -> None:
        """Select the primary record field when byte $1A is nonzero."""

        report = prove_three_d_snapshot(_snapshot(state=0xFF))
        self.assertEqual(report["record"]["selected_offset"], "0x00")
        self.assertEqual(report["record"]["selected_text"], "魔矢")

    def test_wrong_logical_pc_is_rejected(self) -> None:
        """Reject a stop that is not at the $3D success-path address."""

        good = _snapshot()
        wrong = LiveSnapshot(0x958F, good.a, good.mprs, good.memory)
        with self.assertRaisesRegex(ValueError, "expected PC"):
            prove_three_d_snapshot(wrong)

    def test_wrong_accumulator_is_rejected(self) -> None:
        """Reject a $9593 stop whose accumulator is not opcode $3D."""

        good = _snapshot()
        wrong = LiveSnapshot(good.pc, 0x81, good.mprs, good.memory)
        with self.assertRaisesRegex(ValueError, "expected A"):
            prove_three_d_snapshot(wrong)

    def test_wrong_bank_mapping_is_rejected(self) -> None:
        """Reject logical $9593 when MPR4 does not map the proven bank."""

        good = _snapshot()
        mprs = list(good.mprs)
        mprs[4] = 0x83
        wrong = LiveSnapshot(
            good.pc,
            good.a,
            tuple(mprs),
            good.memory,
        )
        with self.assertRaisesRegex(
            ValueError,
            "not the proven Mission 0 interpreter",
        ):
            prove_three_d_snapshot(wrong)

    def test_memory_must_be_frozen_bytes(self) -> None:
        """Reject mutable bytearray snapshots before evidence generation."""

        good = _snapshot()
        with self.assertRaisesRegex(TypeError, "memory must be bytes"):
            LiveSnapshot(
                good.pc,
                good.a,
                good.mprs,
                bytearray(good.memory),  # type: ignore[arg-type]
            )

    def test_loader_accepts_hex_string_metadata(self) -> None:
        """Parse base-prefixed register and MPR strings from JSON metadata."""

        good = _snapshot(state=0xFF)
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            metadata = root / "snapshot.json"
            memory = root / "memory.bin"
            metadata.write_text(
                json.dumps(
                    {
                        "pc": "0x9593",
                        "a": "0x3D",
                        "mprs": [f"0x{x:02X}" for x in good.mprs],
                    }
                ),
                encoding="utf-8",
            )
            memory.write_bytes(good.memory)
            loaded = load_snapshot(metadata, memory)
        self.assertEqual(loaded.pc, 0x9593)
        self.assertEqual(loaded.a, 0x3D)
        self.assertEqual(loaded.mprs[4], 0x82)


if __name__ == "__main__":
    unittest.main()
