"""Shared benchmark reporting helpers.

Benchmarks intentionally live outside the installed package.  Each timed sample
runs in a fresh child process so process peak RSS is meaningful and Numba cold
versus warm behavior can be isolated.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

MIB = 1024 * 1024
AUTHENTICATED_PAYLOAD_BYTES = 84_375_552
AUTHENTICATED_PAYLOAD_SHA256 = (
    "0817cfa03fedc7b33c52f9bd9423b41480fa385cff3693262732b8768e7ca223"
)


def process_peak_rss_mib() -> float:
    """Return this process's peak resident set size in MiB when available."""

    if sys.platform.startswith("linux"):
        try:
            for line in pathlib.Path("/proc/self/status").read_text().splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024.0
        except OSError:
            pass
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return value / MIB
        return value / 1024.0
    except (ImportError, OSError):
        return float("nan")


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    """Aggregate one benchmark case across isolated-process samples."""

    name: str
    median_seconds: float
    mad_seconds: float
    mib_per_second: float | None
    rows_per_second: float | None
    median_peak_rss_mib: float
    rows: int | None
    output_sha256: str | None
    samples: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable benchmark record."""

        return {
            "name": self.name,
            "median_seconds": self.median_seconds,
            "mad_seconds": self.mad_seconds,
            "mib_per_second": self.mib_per_second,
            "rows_per_second": self.rows_per_second,
            "median_peak_rss_mib": self.median_peak_rss_mib,
            "rows": self.rows,
            "output_sha256": self.output_sha256,
            "samples": self.samples,
        }


def authenticated_payload(parser: argparse.ArgumentParser, value: str | None) -> pathlib.Path:
    """Resolve and authenticate the benchmark payload before spawning workers."""

    from cyber_oedo.io import sha256_file

    raw = value or os.environ.get("CYBER_CITY_TRACK2_PAYLOAD")
    if not raw:
        parser.error(
            "supply --payload or CYBER_CITY_TRACK2_PAYLOAD with the authenticated Track-2 payload"
        )
    path = pathlib.Path(raw).resolve()
    if path.stat().st_size != AUTHENTICATED_PAYLOAD_BYTES:
        parser.error(f"unexpected payload size: {path.stat().st_size}")
    digest = sha256_file(path)
    if digest != AUTHENTICATED_PAYLOAD_SHA256:
        parser.error(f"unexpected payload SHA-256: {digest}")
    return path


def run_worker(
    script: pathlib.Path,
    case: str,
    payload: pathlib.Path,
    *,
    extra: tuple[str, ...] = (),
    cold_numba: bool = False,
) -> dict[str, Any]:
    """Run one isolated worker and decode its final JSON line."""

    environment = os.environ.copy()
    if cold_numba:
        environment["NUMBA_CACHE_DIR"] = tempfile.mkdtemp(prefix="cyber-oedo-numba-")
    command = [
        sys.executable,
        str(script),
        "--worker",
        case,
        "--payload",
        str(payload),
        *extra,
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"benchmark worker {case!r} produced no result")
    return json.loads(lines[-1])


def summarize(
    name: str,
    records: list[dict[str, Any]],
    *,
    input_bytes: int | None = None,
) -> BenchmarkSummary:
    """Aggregate wall-time, MAD, throughput, RSS, rows, and identity."""

    if not records:
        raise ValueError("at least one benchmark record is required")
    times = [float(item["seconds"]) for item in records]
    median = statistics.median(times)
    mad = statistics.median(abs(value - median) for value in times)
    rss = statistics.median(float(item["peak_rss_mib"]) for item in records)
    rows_values = {item.get("rows") for item in records}
    if len(rows_values) != 1:
        raise AssertionError(f"{name}: row count changed across samples")
    rows = next(iter(rows_values))
    hashes = {item.get("output_sha256") for item in records}
    if len(hashes) != 1:
        raise AssertionError(f"{name}: output identity changed across samples")
    digest = next(iter(hashes))
    mib_per_second = None
    if input_bytes is not None:
        mib_per_second = (input_bytes / MIB) / median
    rows_per_second = None
    if rows is not None:
        rows_per_second = int(rows) / median
    return BenchmarkSummary(
        name=name,
        median_seconds=median,
        mad_seconds=mad,
        mib_per_second=mib_per_second,
        rows_per_second=rows_per_second,
        median_peak_rss_mib=rss,
        rows=int(rows) if rows is not None else None,
        output_sha256=str(digest) if digest is not None else None,
        samples=len(records),
    )


def print_report(summaries: list[BenchmarkSummary]) -> None:
    """Print machine-readable records and a compact Markdown table."""

    print(json.dumps([item.to_dict() for item in summaries], indent=2))
    print()
    print("| case | median ms | MAD ms | MiB/s | rows/s | peak RSS MiB | rows |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for item in summaries:
        mib = "-" if item.mib_per_second is None else f"{item.mib_per_second:.1f}"
        rows_per_second = (
            "-" if item.rows_per_second is None else f"{item.rows_per_second:,.0f}"
        )
        rows = "-" if item.rows is None else f"{item.rows:,}"
        print(
            f"| {item.name} | {item.median_seconds * 1000:.2f} | "
            f"{item.mad_seconds * 1000:.2f} | {mib} | {rows_per_second} | "
            f"{item.median_peak_rss_mib:.1f} | {rows} |"
        )
