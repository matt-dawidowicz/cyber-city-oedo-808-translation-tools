#!/usr/bin/env python3
"""Benchmark Tier-A analysis paths and verify stable artifact identities."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import time

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
from cyber_oedo.analysis import build_resource_map, scan_likely_sjis
from cyber_oedo.text import (
    build_translation_inventory,
    extract_auxiliary_text,
    extract_dialogue,
    validate_translation_inventory,
)

ARTIFACTS = (
    "resource_map.tsv",
    "likely_sjis.tsv",
    "dialogue.tsv",
    "auxiliary.tsv",
    "translation_inventory.tsv",
)


def _digest_artifacts(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for name in ARTIFACTS:
        path = root / name
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _row_count(root: pathlib.Path) -> int:
    return sum(
        max(
            0,
            len((root / name).read_text(encoding="utf-8-sig").splitlines()) - 1,
        )
        for name in ARTIFACTS
    )


def _run_legacy(payload: pathlib.Path, root: pathlib.Path) -> None:
    resource = root / "resource_map.tsv"
    likely = root / "likely_sjis.tsv"
    dialogue = root / "dialogue.tsv"
    auxiliary = root / "auxiliary.tsv"
    inventory = root / "translation_inventory.tsv"
    build_resource_map.main([str(payload), str(resource)])
    scan_likely_sjis.main([str(payload), str(likely)])
    extract_dialogue.main([str(payload), str(dialogue)])
    extract_auxiliary_text.main([str(likely), str(dialogue), str(auxiliary)])
    build_translation_inventory.main([str(dialogue), str(auxiliary), str(inventory)])
    result = validate_translation_inventory.main([str(inventory)])
    if result:
        raise RuntimeError("generated inventory failed validation")


def _run_orchestrated(payload: pathlib.Path, root: pathlib.Path) -> None:
    from cyber_oedo.analysis.pipeline import run_analysis

    result = run_analysis(payload, root, build_database=False)
    if result.validation_errors:
        raise RuntimeError("orchestrated inventory failed validation")


def _worker(case: str, payload: pathlib.Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="cyber-oedo-bench-") as directory:
        root = pathlib.Path(directory)
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            started = time.perf_counter()
            if case == "legacy":
                _run_legacy(payload, root)
            elif case == "orchestrated":
                _run_orchestrated(payload, root)
            else:
                raise ValueError(f"unknown benchmark case: {case}")
            seconds = time.perf_counter() - started
        return {
            "seconds": seconds,
            "rows": _row_count(root),
            "peak_rss_mib": process_peak_rss_mib(),
            "output_sha256": _digest_artifacts(root),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument(
        "--case",
        choices=("legacy", "orchestrated", "both"),
        default="both",
    )
    parser.add_argument("--worker", choices=("legacy", "orchestrated"))
    args = parser.parse_args()
    payload = authenticated_payload(parser, args.payload)
    if args.worker:
        print(json.dumps(_worker(args.worker, payload), separators=(",", ":")))
        return 0
    if args.samples <= 0:
        parser.error("--samples must be positive")

    script = pathlib.Path(__file__).resolve()
    cases = ("legacy", "orchestrated") if args.case == "both" else (args.case,)
    summaries = []
    for case in cases:
        records = [run_worker(script, case, payload) for _ in range(args.samples)]
        summaries.append(
            summarize(case, records, input_bytes=AUTHENTICATED_PAYLOAD_BYTES)
        )
    if len(summaries) == 2:
        left, right = summaries
        if (left.rows, left.output_sha256) != (right.rows, right.output_sha256):
            raise AssertionError("legacy and orchestrated Tier-A outputs differ")
    print_report(summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
