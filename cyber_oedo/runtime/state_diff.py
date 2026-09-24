"""Compare two frozen HuC6280 logical-memory snapshots.

This diagnostic is intentionally generic and read-only. It is designed for
Tier-B runtime archaeology where the same logical address can refer to different
physical 8 KiB pages under different MPR mappings.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from dataclasses import dataclass
from typing import Any

from cyber_oedo.io import sha256_buffer
from cyber_oedo.runtime.live_snapshot import CPU_ADDRESS_SPACE, MPR_COUNT, MPR_WINDOW_BYTES


DEFAULT_MAX_RUNS = 256


@dataclass(frozen=True, slots=True)
class SnapshotState:
    """One labeled frozen logical-memory state plus its MPR mapping."""

    label: str
    mprs: tuple[int, ...]
    memory: bytes

    def __post_init__(self) -> None:
        if len(self.mprs) != MPR_COUNT:
            raise ValueError("exactly eight MPR values are required")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in self.mprs):
            raise TypeError("MPR values must be integers")
        if any(not 0 <= value <= 0xFF for value in self.mprs):
            raise ValueError("MPR values must fit in one byte")
        if len(self.memory) != CPU_ADDRESS_SPACE:
            raise ValueError("logical CPU memory dump must be exactly 65536 bytes")


def _parse_number(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer or numeric string")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"{name} is empty")
        return int(text, 0)
    raise TypeError(f"{name} must be an integer or numeric string")


def physical_address(cpu_address: int, mprs: tuple[int, ...]) -> str:
    """Format one logical address using the supplied HuC6280 MPR state."""

    if not 0 <= cpu_address < CPU_ADDRESS_SPACE:
        raise ValueError("CPU address must fit in 16 bits")
    slot = cpu_address // MPR_WINDOW_BYTES
    page = mprs[slot]
    offset = cpu_address & (MPR_WINDOW_BYTES - 1)
    return f"*{page:02X}:{offset:04X}"


def _changed_runs(before: bytes, after: bytes) -> tuple[tuple[int, int], ...]:
    """Return half-open contiguous logical ranges whose bytes changed."""

    runs: list[tuple[int, int]] = []
    start: int | None = None
    for address, (left, right) in enumerate(zip(before, after)):
        if left != right:
            if start is None:
                start = address
        elif start is not None:
            runs.append((start, address))
            start = None
    if start is not None:
        runs.append((start, len(before)))
    return tuple(runs)


def compare_states(
    before: SnapshotState,
    after: SnapshotState,
    *,
    max_runs: int = DEFAULT_MAX_RUNS,
) -> dict[str, Any]:
    """Build deterministic bank-aware evidence for one state transition."""

    if max_runs < 1:
        raise ValueError("max_runs must be positive")

    runs = _changed_runs(before.memory, after.memory)
    changed_bytes = sum(end - start for start, end in runs)
    rendered_runs: list[dict[str, Any]] = []
    for start, end in runs[:max_runs]:
        rendered_runs.append(
            {
                "start": f"0x{start:04X}",
                "end_exclusive": f"0x{end:04X}",
                "bytes": end - start,
                "before_physical": physical_address(start, before.mprs),
                "after_physical": physical_address(start, after.mprs),
                "before_hex": before.memory[start:end].hex(),
                "after_hex": after.memory[start:end].hex(),
            }
        )

    mpr_changes = [
        {
            "slot": index,
            "before": f"0x{left:02X}",
            "after": f"0x{right:02X}",
        }
        for index, (left, right) in enumerate(zip(before.mprs, after.mprs))
        if left != right
    ]

    return {
        "proof": "bank-aware-live-state-diff",
        "before_label": before.label,
        "after_label": after.label,
        "before_memory_sha256": sha256_buffer(before.memory),
        "after_memory_sha256": sha256_buffer(after.memory),
        "before_mprs": [f"0x{value:02X}" for value in before.mprs],
        "after_mprs": [f"0x{value:02X}" for value in after.mprs],
        "mpr_changes": mpr_changes,
        "changed_bytes": changed_bytes,
        "changed_runs": len(runs),
        "reported_runs": len(rendered_runs),
        "truncated": len(runs) > len(rendered_runs),
        "runs": rendered_runs,
    }


def _load_metadata(path: pathlib.Path) -> tuple[str, tuple[int, ...]]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    raw_mprs = metadata.get("mprs", metadata.get("mpr"))
    if not isinstance(raw_mprs, list):
        raise ValueError("snapshot metadata must contain an mprs array")
    label = metadata.get("label", path.stem)
    if not isinstance(label, str) or not label:
        raise ValueError("snapshot label must be a non-empty string")
    mprs = tuple(
        _parse_number(value, f"mprs[{index}]")
        for index, value in enumerate(raw_mprs)
    )
    return label, mprs


def load_state(metadata_path: pathlib.Path, memory_path: pathlib.Path) -> SnapshotState:
    """Load one labeled frozen state from metadata and a 64 KiB memory dump."""

    label, mprs = _load_metadata(metadata_path)
    return SnapshotState(label=label, mprs=mprs, memory=memory_path.read_bytes())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two bank-aware 64 KiB HuC6280 snapshots and report "
            "contiguous logical-memory changes."
        )
    )
    parser.add_argument("before_metadata", type=pathlib.Path)
    parser.add_argument("before_memory", type=pathlib.Path)
    parser.add_argument("after_metadata", type=pathlib.Path)
    parser.add_argument("after_memory", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--max-runs", type=int, default=DEFAULT_MAX_RUNS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = compare_states(
        load_state(args.before_metadata, args.before_memory),
        load_state(args.after_metadata, args.after_memory),
        max_runs=args.max_runs,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
