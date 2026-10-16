"""Instruction-level synthetic checks for the experimental HuC6280 pool helper.

This is a deliberately limited CPU model, NOT an emulator or real-game proof.
It executes the generated helper bytecode, models MPR3's mapping window, and
stubs System Card CD_READ to detect incorrect transfer arguments.
"""

from __future__ import annotations

import unittest

from cyber_oedo.runtime.mission0_pool_pilot import (
    M0B_POOL_LAYOUT, POOL_START_ABSOLUTE_LBA, _make_runtime,
)
from cyber_oedo.text.english_dialogue_engine import EnglishGlyphTable
from cyber_oedo.text.font_atlas import RasterConfig, RasterizedAtlas


class PilotCPU:
    def __init__(self, code: bytes, labels: dict[str, int],
                 pool: bytes, *, bios_failure_index: int | None = None) -> None:
        self.memory = bytearray(65536)
        self.memory[M0B_POOL_LAYOUT.code_cpu:
                    M0B_POOL_LAYOUT.code_cpu + len(code)] = code
        self.labels = labels
        self.dp = bytearray(256)
        self.stack = bytearray(256)
        self.sp = 255
        self.a = 0
        self.x = 0
        self.y = 0
        self.c = 0
        self.z = False
        self.interrupts_disabled = False
        self.pc = 0
        self.mpr3 = 0x81
        self.banks = {bank: bytearray(0x2000) for bank in range(0x7C, 0x80)}
        self.source_pool = pool
        self.cd_reads: list[tuple[int, int, int, int]] = []
        self.bios_failure_index = bios_failure_index
        # Physically install the 3- and 6-byte stock helper trampolines.
        for at, name, count in (
            (0x9F11, "pool_read", 3),
            (0x9F14, "pool_advance", 6),
        ):
            target = labels[name]
            self.memory[at:at + count] = bytes(
                (0x4C, target & 255, target >> 8)
            ) + bytes((0xEA,)) * (count - 3)

    def nz(self, value: int) -> int:
        value &= 255
        self.z = value == 0
        return value

    def push(self, value: int) -> None:
        self.stack[self.sp] = value & 255
        self.sp = (self.sp - 1) & 255

    def pop(self) -> int:
        self.sp = (self.sp + 1) & 255
        return self.stack[self.sp]

    def read(self, address: int) -> int:
        address &= 0xFFFF
        if 0x6000 <= address < 0x8000 and self.mpr3 in self.banks:
            return self.banks[self.mpr3][address - 0x6000]
        return self.memory[address]

    def write(self, address: int, value: int) -> None:
        address &= 0xFFFF
        if 0x6000 <= address < 0x8000 and self.mpr3 in self.banks:
            self.banks[self.mpr3][address - 0x6000] = value & 255
        else:
            self.memory[address] = value & 255

    def fetch(self) -> int:
        out = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return out

    def addr(self) -> int:
        low = self.fetch()
        return low | (self.fetch() << 8)

    def _flags(self) -> int:
        return ((self.c & 1) | (0x02 if self.z else 0)
                | (0x04 if self.interrupts_disabled else 0) | 0x20)

    def _restore_flags(self, value: int) -> None:
        self.c = value & 1
        self.z = bool(value & 2)
        self.interrupts_disabled = bool(value & 4)

    def _bios_cd_read(self) -> None:
        lba = (self.dp[0xFC] << 16) | (self.dp[0xFD] << 8) | self.dp[0xFE]
        count = self.dp[0xF8] | (self.dp[0xF9] << 8)
        destination = self.dp[0xFA] | (self.dp[0xFB] << 8)
        self.cd_reads.append((lba, count, destination, self.mpr3))
        if self.bios_failure_index == len(self.cd_reads):
            self.a = self.nz(3)
        else:
            if not (
                POOL_START_ABSOLUTE_LBA <= lba <= POOL_START_ABSOLUTE_LBA + 12
                and count == 4
                and destination == 0x6000
                and self.dp[0xFF] == 1
                and self.mpr3 in self.banks
            ):
                raise AssertionError("BIOS read arguments violate pool contract")
            start = (lba - POOL_START_ABSOLUTE_LBA) * 2048
            self.banks[self.mpr3][:] = self.source_pool[start:start + 0x2000]
            self.a = self.nz(0)
        last = self.pop()
        self.pc = ((self.pop() << 8) | last) + 1

    def step(self) -> None:
        if self.pc == 0xE009:
            self._bios_cd_read()
            return
        op_at = self.pc
        op = self.fetch()
        if op == 0xA9:
            self.a = self.nz(self.fetch())
        elif op == 0xA2:
            self.x = self.nz(self.fetch())
        elif op == 0xAD:
            self.a = self.nz(self.read(self.addr()))
        elif op == 0xBD:
            self.a = self.nz(self.read(self.addr() + self.x))
        elif op == 0xB5:
            self.a = self.nz(self.dp[(self.fetch() + self.x) & 255])
        elif op == 0xB2:
            zp = self.fetch()
            self.a = self.nz(self.read(self.dp[zp] | (self.dp[(zp + 1) & 255] << 8)))
        elif op == 0xA5:
            self.a = self.nz(self.dp[self.fetch()])
        elif op == 0x8D:
            self.write(self.addr(), self.a)
        elif op == 0x9D:
            self.write(self.addr() + self.x, self.a)
        elif op == 0x85:
            self.dp[self.fetch()] = self.a
        elif op == 0x95:
            self.dp[(self.fetch() + self.x) & 255] = self.a
        elif op == 0x9C:
            self.write(self.addr(), 0)
        elif op == 0xEE:
            addr = self.addr()
            self.write(addr, self.nz(self.read(addr) + 1))
        elif op == 0xE6:
            at = self.fetch()
            self.dp[at] = self.nz(self.dp[at] + 1)
        elif op == 0xE8:
            self.x = self.nz(self.x + 1)
        elif op == 0xC9:
            v = self.fetch()
            self.c = 1 if self.a >= v else 0
            self.z = self.a == v
        elif op == 0xE0:
            v = self.fetch()
            self.c = 1 if self.x >= v else 0
            self.z = self.x == v
        elif op in (0xF0, 0xD0, 0xB0, 0x90, 0x80):
            b = self.fetch()
            relative = b if b < 0x80 else b - 256
            take = {0xF0: self.z, 0xD0: not self.z,
                    0xB0: bool(self.c), 0x90: not self.c,
                    0x80: True}[op]
            if take:
                self.pc = (self.pc + relative) & 0xFFFF
        elif op == 0x4C:
            self.pc = self.addr()
        elif op == 0x20:
            addr = self.addr()
            at = (self.pc - 1) & 0xFFFF
            self.push(at >> 8)
            self.push(at & 255)
            self.pc = addr
        elif op == 0x60:
            low = self.pop()
            self.pc = (((self.pop() << 8) | low) + 1) & 0xFFFF
        elif op == 0x48:
            self.push(self.a)
        elif op == 0x68:
            self.a = self.nz(self.pop())
        elif op == 0x08:
            self.push(self._flags())
        elif op == 0x28:
            self._restore_flags(self.pop())
        elif op == 0xDA:
            self.push(self.x)
        elif op == 0x5A:
            self.push(self.y)
        elif op == 0xFA:
            self.x = self.nz(self.pop())
        elif op == 0x7A:
            self.y = self.nz(self.pop())
        elif op == 0x78:
            self.interrupts_disabled = True
        elif op == 0x43:
            if self.fetch() != 0x08:
                raise AssertionError("only MPR3 is modeled")
            self.a = self.nz(self.mpr3)
        elif op == 0x53:
            if self.fetch() != 0x08:
                raise AssertionError("only MPR3 is modeled")
            self.mpr3 = self.a
        elif op == 0x18:
            self.c = 0
        elif op == 0x69:
            x = self.a + self.fetch() + self.c
            self.c = int(x > 255)
            self.a = self.nz(x)
        elif op == 0x6D:
            x = self.a + self.read(self.addr()) + self.c
            self.c = int(x > 255)
            self.a = self.nz(x)
        elif op == 0x29:
            self.a = self.nz(self.a & self.fetch())
        elif op == 0x09:
            self.a = self.nz(self.a | self.fetch())
        elif op == 0x0A:
            self.c = int(self.a >= 128)
            self.a = self.nz(self.a << 1)
        elif op == 0x4A:
            self.c = self.a & 1
            self.a = self.nz(self.a >> 1)
        elif op == 0xEA:
            return
        else:
            raise AssertionError(
                f"unsupported synthetic CPU opcode {op:02X} at {op_at:04X}"
            )

    def until(self, destination: int, *, max_steps: int = 20000) -> None:
        for _ in range(max_steps):
            if self.pc == destination:
                return
            self.step()
        raise AssertionError(f"pilot bytecode did not reach {destination:04X}")

    def subroutine(self, label: str) -> int:
        # JSR would push the last operand address, RTS adds one.
        self.push(0xFF)  # high byte of synthetic JSR return ($FFFD)
        self.push(0xFD)
        self.pc = self.labels[label]
        self.until(0xFFFE)
        return self.a

    def active(self) -> int:
        return self.memory[self.labels["active"]]

    def script_ptr(self) -> int:
        return self.dp[0x7F] | (self.dp[0x80] << 8)


class Mission0PoolCpuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        chars = " ?Bartend:Wlcom."
        glyphs = EnglishGlyphTable(chars)
        atlas = RasterizedAtlas(
            characters=chars,
            glyphs=tuple(bytes(16) for _ in chars),
            source_sha256="0" * 64,
            config=RasterConfig(),
        )
        runtime = _make_runtime(glyphs, atlas)
        cls.code = runtime.full_code
        cls.labels = runtime.labels

    def _cpu(self, *, offset: int = 0, fail: int | None = None) -> PilotCPU:
        pool = bytearray(0x8000)
        pool[offset:offset + 6] = bytes.fromhex("7D 45 80 81 7C 00")
        cpu = PilotCPU(self.code, self.labels, bytes(pool),
                       bios_failure_index=fail)
        # Source pointer after interpreter consumed opcode 7B; two-byte
        # pool offset, 2-byte remaining-source skip, 23 old glyph bytes, 00.
        original = offset.to_bytes(2, "little") + (23).to_bytes(2, "little")
        cpu.memory[0x8000:0x8000 + 28] = original + bytes((0x81,)) * 23 + b"\x00"
        cpu.dp[0x7F] = 0x00
        cpu.dp[0x80] = 0x80
        cpu.a = 0x7B
        return cpu

    def test_dispatch_reads_all_four_pool_banks_without_clobbering_stock_mpr3(self) -> None:
        cpu = self._cpu()
        cpu.dp[0xF8:0x100] = bytes.fromhex("10 11 12 13 14 15 16 17")
        cpu.pc = cpu.labels["pool_dispatch"]
        cpu.until(0x9549)
        self.assertEqual(cpu.active(), 1)
        self.assertEqual(cpu.script_ptr(), 0x6001)
        self.assertEqual(cpu.mpr3, 0x81)
        self.assertEqual(
            cpu.cd_reads,
            [(POOL_START_ABSOLUTE_LBA + 4 * i, 4, 0x6000, 0x7C + i)
             for i in range(4)],
        )
        self.assertEqual(
            bytes(cpu.dp[0xF8:0x100]),
            bytes.fromhex("10 11 12 13 14 15 16 17"),
        )
        self.assertEqual(cpu.memory[cpu.labels["source_lo"]], 0x1B)
        self.assertEqual(cpu.memory[cpu.labels["source_hi"]], 0x80)
        self.assertEqual(cpu.subroutine("pool_read"), 0x45)
        self.assertEqual(cpu.mpr3, 0x81)

    def test_pool_terminator_restores_original_continuation(self) -> None:
        cpu = self._cpu()
        cpu.pc = cpu.labels["pool_dispatch"]
        cpu.until(0x9549)
        cpu.dp[0x7F], cpu.dp[0x80] = 0x05, 0x60
        cpu.pc = cpu.labels["pool_parser_entry"]
        cpu.until(0x9549)
        self.assertEqual(cpu.active(), 0)
        self.assertEqual(cpu.script_ptr(), 0x801C)
        self.assertEqual(cpu.a, 0)
        self.assertEqual(cpu.mpr3, 0x81)

    def test_pool_bank_rollover_does_not_map_over_stock_mpr3_code(self) -> None:
        cpu = self._cpu(offset=0x1FFF)
        cpu.pc = cpu.labels["pool_dispatch"]
        cpu.until(0x9549)
        # Parser-entry has *already* read the byte at $7FFF and
        # advanced across the bank boundary before reaching $9549.
        self.assertEqual(cpu.script_ptr(), 0x6000)
        self.assertEqual(cpu.memory[cpu.labels["pool_bank"]], 0x7D)
        cpu.dp[0x7F], cpu.dp[0x80] = 0xFF, 0x7F
        cpu.memory[cpu.labels["pool_bank"]] = 0x7C
        self.assertEqual(cpu.subroutine("pool_read"), 0x7D)
        a_before = cpu.a
        cpu.subroutine("pool_advance")
        self.assertEqual(cpu.a, a_before)
        self.assertEqual(cpu.script_ptr(), 0x6000)
        self.assertEqual(cpu.memory[cpu.labels["pool_bank"]], 0x7D)
        self.assertEqual(cpu.subroutine("pool_read"), 0x45)
        self.assertEqual(cpu.mpr3, 0x81)

    def test_bios_error_fails_closed_at_original_terminator(self) -> None:
        cpu = self._cpu(fail=2)
        cpu.pc = cpu.labels["pool_dispatch"]
        cpu.until(0x9549)
        self.assertEqual(cpu.active(), 0)
        self.assertEqual(cpu.script_ptr(), 0x801C)
        self.assertEqual(len(cpu.cd_reads), 2)
        self.assertEqual(cpu.mpr3, 0x81)


if __name__ == "__main__":
    unittest.main()
