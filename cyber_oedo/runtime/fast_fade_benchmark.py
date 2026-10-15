"""Benchmark-only Mission 0 fast audio teardown patch.

The stock dialogue transition uses module command 2 at logical $80E7:

* PSG_FDOUT;
* CD_FADE mode $0E; and
* a later outer wait for $37F0 to clear.

For an A/B timing experiment, replace command 2 with:

    JSR $E042   ; AD_STOP
    JMP $813E   ; existing command-5 cleanup

Command 5 is the game's own immediate PSG/state teardown path.  Jumping to it
preserves its normal RTS back to the original command dispatcher caller.

This patch is deliberately *not* release policy.  It hard-cuts transition
audio so we can measure how much of the multi-second pause is attributable to
the fade gate.  Promotion requires live timing plus audio/state validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from cyber_oedo.disc.cdrom_mode1 import PayloadPatch
from cyber_oedo.runtime.dialogue_interpreter import TRACK2_PAYLOAD_SHA256

SECTOR_BYTES = 0x800
TRACK2_START_LBA = 3590

DIALOGUE_MODULE_LBA = 0x1425
FADE_COMMAND_CPU = 0x80E7
FADE_COMMAND_RELATIVE = FADE_COMMAND_CPU - 0x8000
FADE_COMMAND_PAYLOAD_OFFSET = (
    (DIALOGUE_MODULE_LBA - TRACK2_START_LBA) * SECTOR_BYTES
    + FADE_COMMAND_RELATIVE
)

FADE_COMMAND_EXPECTED = bytes.fromhex(
    "AD F0 37 F0 13 C9 FF F0 0F A9 FF 8D F0 37 "
    "A9 1E 20 F7 81 A9 0E 20 2D E0 60"
)
_FAST_TEARDOWN = bytes.fromhex(
    "20 42 E0 "  # JSR $E042, AD_STOP
    "4C 3E 81"  # JMP $813E, stock command-5 cleanup
)
FADE_COMMAND_REPLACEMENT = _FAST_TEARDOWN + bytes(
    (0xEA,)
) * (len(FADE_COMMAND_EXPECTED) - len(_FAST_TEARDOWN))


@dataclass(frozen=True, slots=True)
class FastFadeBenchmark:
    """Describe the exact source-guarded benchmark mutation."""

    patch: PayloadPatch

    @property
    def changed_bytes(self) -> int:
        """Return the number of payload bytes that differ from stock."""

        return sum(
            before != after
            for before, after in zip(
                self.patch.expected,
                self.patch.replacement,
                strict=True,
            )
        )


def build_fast_fade_benchmark_patch() -> FastFadeBenchmark:
    """Build the fixed-size benchmark patch for module command 2."""

    return FastFadeBenchmark(
        PayloadPatch(
            offset=FADE_COMMAND_PAYLOAD_OFFSET,
            expected=FADE_COMMAND_EXPECTED,
            replacement=FADE_COMMAND_REPLACEMENT,
            label=(
                "Mission 0 benchmark: replace long transition fade with "
                "AD_STOP plus stock immediate command-5 cleanup"
            ),
        )
    )


def validate_fast_fade_source(payload: bytes) -> dict[str, object]:
    """Validate payload identity and exact command-2 source bytes."""

    import hashlib

    digest = hashlib.sha256(payload).hexdigest()
    benchmark = build_fast_fade_benchmark_patch()
    patch = benchmark.patch
    actual = payload[patch.offset : patch.end_offset]
    return {
        "payload_sha256": digest,
        "payload_authenticated": digest == TRACK2_PAYLOAD_SHA256,
        "fade_command_offset": f"0x{patch.offset:08X}",
        "fade_command_source_match": actual == patch.expected,
        "benchmark_changed_bytes": benchmark.changed_bytes,
        "replacement_hex": patch.replacement.hex(" ").upper(),
        "release_enabled": False,
    }
