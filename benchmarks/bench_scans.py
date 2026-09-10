#!/usr/bin/env python3
"""Benchmark native Track-2 scan hot paths with exact-output identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from collections.abc import Iterator

import numpy as np

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from _common import (
    AUTHENTICATED_PAYLOAD_BYTES,
    authenticated_payload,
    print_report,
    process_peak_rss_mib,
    run_worker,
    summarize,
)
from cyber_oedo.analysis.fast_scan import (
    broad_sjis_runs,
    decodable_broad_sjis_runs,
    likely_sjis_runs,
    sector_metrics,
)
from cyber_oedo.analysis.scan_track import scan_shift_jis
from cyber_oedo.disc.game_layout import SECTOR_SIZE
from cyber_oedo.io import mapped_file


def _array_digest(*arrays: np.ndarray) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(memoryview(array).cast("B"))
    return digest.hexdigest()


def _legacy_decoded_rows(data: object) -> Iterator[tuple[int, int, str]]:
    """Reproduce the pre-filter broad discovery/decode path for A/B timing."""

    starts, ends, counts = broad_sjis_runs(data, 3)
    for start, end, japanese in zip(starts, ends, counts, strict=True):
        offset = int(start)
        raw = data[offset : int(end)]  # type: ignore[index]
        try:
            text = raw.decode("shift_jis")
        except UnicodeDecodeError:
            continue
        yield (
            offset,
            int(japanese),
            text.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t"),
        )


def _digest_decoded_rows(rows: Iterator[tuple[int, int, str]]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for offset, japanese, text in rows:
        digest.update(offset.to_bytes(8, "little"))
        digest.update(japanese.to_bytes(4, "little"))
        encoded = text.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        count += 1
    return count, digest.hexdigest()


def _worker(case: str, payload: pathlib.Path) -> dict[str, object]:
    with mapped_file(payload) as data:
        if case == "sector-warm":
            sector_metrics(data, SECTOR_SIZE)
            operation = lambda: sector_metrics(data, SECTOR_SIZE)
        elif case == "sector-cold":
            operation = lambda: sector_metrics(data, SECTOR_SIZE)
        elif case == "broad-warm":
            broad_sjis_runs(data, 3)
            operation = lambda: broad_sjis_runs(data, 3)
        elif case == "broad-cold":
            operation = lambda: broad_sjis_runs(data, 3)
        elif case == "likely-warm":
            likely_sjis_runs(data, 4)
            operation = lambda: likely_sjis_runs(data, 4)
        elif case == "likely-cold":
            operation = lambda: likely_sjis_runs(data, 4)
        elif case in {
            "decoded-broad-legacy",
            "decoded-broad-native-warm",
            "decoded-broad-native-cold",
        }:
            if case == "decoded-broad-legacy":
                broad_sjis_runs(data, 3)
                decoded = lambda: _legacy_decoded_rows(data)
            else:
                if case.endswith("warm"):
                    decodable_broad_sjis_runs(data, 3)
                decoded = lambda: scan_shift_jis(data, 3)
            started = time.perf_counter()
            rows, digest = _digest_decoded_rows(decoded())
            seconds = time.perf_counter() - started
            return {
                "seconds": seconds,
                "rows": rows,
                "peak_rss_mib": process_peak_rss_mib(),
                "output_sha256": digest,
            }
        else:
            raise ValueError(f"unknown benchmark case: {case}")

        started = time.perf_counter()
        arrays = operation()
        seconds = time.perf_counter() - started
        rows = len(arrays[0])
        digest = _array_digest(*arrays)
    return {
        "seconds": seconds,
        "rows": rows,
        "peak_rss_mib": process_peak_rss_mib(),
        "output_sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument(
        "--cold",
        action="store_true",
        help="also measure representative cold Numba startup paths",
    )
    parser.add_argument(
        "--all-cold",
        action="store_true",
        help="measure cold startup for every Numba scan kernel",
    )
    parser.add_argument(
        "--worker",
        choices=(
            "sector-warm",
            "sector-cold",
            "broad-warm",
            "broad-cold",
            "likely-warm",
            "likely-cold",
            "decoded-broad-legacy",
            "decoded-broad-native-warm",
            "decoded-broad-native-cold",
        ),
    )
    args = parser.parse_args()
    payload = authenticated_payload(parser, args.payload)
    if args.worker:
        print(json.dumps(_worker(args.worker, payload), separators=(",", ":")))
        return 0
    if args.samples <= 0:
        parser.error("--samples must be positive")

    script = pathlib.Path(__file__).resolve()
    summaries = []
    warm_cases = (
        "sector-warm",
        "broad-warm",
        "likely-warm",
        "decoded-broad-legacy",
        "decoded-broad-native-warm",
    )
    for case in warm_cases:
        records = [run_worker(script, case, payload) for _ in range(args.samples)]
        summaries.append(
            summarize(case, records, input_bytes=AUTHENTICATED_PAYLOAD_BYTES)
        )

    legacy = next(item for item in summaries if item.name == "decoded-broad-legacy")
    native = next(
        item for item in summaries if item.name == "decoded-broad-native-warm"
    )
    if (legacy.rows, legacy.output_sha256) != (native.rows, native.output_sha256):
        raise AssertionError("native broad-SJIS filtering changed decoded output")

    cold_cases: list[str] = []
    if args.cold or args.all_cold:
        cold_cases = ["sector-cold", "decoded-broad-native-cold"]
    if args.all_cold:
        cold_cases[1:1] = ["broad-cold", "likely-cold"]
    for case in cold_cases:
        record = run_worker(script, case, payload, cold_numba=True)
        summaries.append(
            summarize(case, [record], input_bytes=AUTHENTICATED_PAYLOAD_BYTES)
        )
    print_report(summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
