#!/usr/bin/env python3
"""Benchmark build planning and guarded Mode-1 patch mutation."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tempfile
import time

REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from _common import authenticated_payload, print_report, process_peak_rss_mib, run_worker, summarize
from cyber_oedo.build.plan import build_profile_plan
from cyber_oedo.build.profiles import mission0_stock as profile
from cyber_oedo.disc.cdrom_mode1 import MODE1_SYNC, PayloadPatch, rebuild_mode1_sector
from cyber_oedo.disc.game_layout import MODE1_USER_DATA_OFFSET, RAW_SECTOR_SIZE, SECTOR_SIZE
from cyber_oedo.disc.patching import apply_payload_patches
from cyber_oedo.io import mapped_file


def _payload_patches() -> tuple[PayloadPatch, ...]:
    """Return the original-title build patch set through the current architecture."""

    try:
        from cyber_oedo.build.recipe import prepare_build_recipe
    except ImportError:
        return tuple(item.to_payload_patch() for item in profile.HUMAN_TEST_PATCHES) + profile.HUMAN_TEST_BINARY_PATCHES
    return prepare_build_recipe("original").payload_patches()


def _synthetic_raw_sector(payload: object, relative_sector: int) -> bytes:
    raw = bytearray(RAW_SECTOR_SIZE)
    raw[: len(MODE1_SYNC)] = MODE1_SYNC
    raw[15] = 1
    start = relative_sector * SECTOR_SIZE
    raw[MODE1_USER_DATA_OFFSET : MODE1_USER_DATA_OFFSET + SECTOR_SIZE] = payload[start : start + SECTOR_SIZE]
    return rebuild_mode1_sector(raw)


def _prepare_sparse_image(path: pathlib.Path, payload: object, patches: tuple[PayloadPatch, ...]) -> tuple[int, ...]:
    sectors = sorted({sector for patch in patches for sector in range(patch.offset // SECTOR_SIZE, (patch.end_offset - 1) // SECTOR_SIZE + 1)})
    with path.open("wb") as output:
        output.truncate(profile.TRACK2_SECTOR_COUNT * RAW_SECTOR_SIZE)
    with path.open("r+b") as output:
        for sector in sectors:
            output.seek(sector * RAW_SECTOR_SIZE)
            output.write(_synthetic_raw_sector(payload, sector))
    return tuple(sectors)


def _digest_sectors(path: pathlib.Path, sectors: tuple[int, ...]) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for sector in sectors:
            source.seek(sector * RAW_SECTOR_SIZE)
            digest.update(source.read(RAW_SECTOR_SIZE))
    return digest.hexdigest()


def _worker(case: str, payload_path: pathlib.Path) -> dict[str, object]:
    if case == "plan":
        iterations = 200
        started = time.perf_counter()
        plan = None
        for _ in range(iterations):
            plan = build_profile_plan("original")
        seconds = (time.perf_counter() - started) / iterations
        assert plan is not None
        return {
            "seconds": seconds,
            "rows": len(plan.entries),
            "peak_rss_mib": process_peak_rss_mib(),
            "output_sha256": plan.sha256(),
        }

    if case != "patch":
        raise ValueError(f"unknown benchmark case: {case}")
    patches = _payload_patches()
    with mapped_file(payload_path) as payload, tempfile.TemporaryDirectory(prefix="cyber-oedo-build-") as directory:
        image = pathlib.Path(directory) / "track.img"
        sectors = _prepare_sparse_image(image, payload, patches)
        started = time.perf_counter()
        reports = apply_payload_patches(
            image,
            patches,
            start_lba=0,
            sector_count=profile.TRACK2_SECTOR_COUNT,
        )
        seconds = time.perf_counter() - started
        if tuple(report.relative_sector for report in reports) != sectors:
            raise AssertionError("patch benchmark sector footprint changed")
        digest = _digest_sectors(image, sectors)
    return {
        "seconds": seconds,
        "rows": len(reports),
        "peak_rss_mib": process_peak_rss_mib(),
        "output_sha256": digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--case", choices=("plan", "patch", "all"), default="all")
    parser.add_argument("--worker", choices=("plan", "patch"))
    args = parser.parse_args()
    payload = authenticated_payload(parser, args.payload)
    if args.worker:
        print(json.dumps(_worker(args.worker, payload), separators=(",", ":")))
        return 0
    if args.samples <= 0:
        parser.error("--samples must be positive")
    script = pathlib.Path(__file__).resolve()
    cases = ("plan", "patch") if args.case == "all" else (args.case,)
    summaries = []
    for case in cases:
        records = [run_worker(script, case, payload) for _ in range(args.samples)]
        summaries.append(summarize(case, records))
    print_report(summaries)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
