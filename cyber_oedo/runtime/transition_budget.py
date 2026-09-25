"""Parse Mesen transition-budget summaries into load-time attribution metrics."""

from __future__ import annotations

import argparse
import json
import pathlib
import re

_BUDGET_RE = re.compile(
    r"\[TRANSITION_BUDGET\].*?"
    r"total_frames=(?P<total>\d+).*?"
    r"cd_read_frames=(?P<cd_read>\d+).*?"
    r"cd_read_calls=(?P<cd_read_calls>\d+).*?"
    r"cd_exec_frames=(?P<cd_exec>\d+).*?"
    r"cd_exec_calls=(?P<cd_exec_calls>\d+).*?"
    r"ad_trans_frames=(?P<ad_trans>\d+).*?"
    r"ad_trans_calls=(?P<ad_trans_calls>\d+).*?"
    r"ad_read_frames=(?P<ad_read>\d+).*?"
    r"ad_read_calls=(?P<ad_read_calls>\d+).*?"
    r"ad_write_frames=(?P<ad_write>\d+).*?"
    r"ad_write_calls=(?P<ad_write_calls>\d+).*?"
    r"fade_wait_frames=(?P<fade_wait>\d+).*?"
    r"vsync_calls=(?P<vsync>\d+).*?"
    r"known_serial_frames=(?P<known>\d+).*?"
    r"residual_frames=(?P<residual>-?\d+)"
)

def parse_transition_budgets(text: str) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for match in _BUDGET_RE.finditer(text):
        values = {key: int(value) for key, value in match.groupdict().items()}
        total = values["total"]
        if total <= 0:
            raise ValueError("transition total must be positive")
        known = (
            values["cd_read"] + values["cd_exec"] + values["ad_trans"]
            + values["ad_read"] + values["ad_write"] + values["fade_wait"]
        )
        if known != values["known"]:
            raise ValueError("known_serial_frames does not match components")
        if total - known != values["residual"]:
            raise ValueError("residual_frames does not match total-components")
        rows.append({
            **values,
            "total_seconds": total / 60.0,
            "cd_read_seconds": values["cd_read"] / 60.0,
            "cd_exec_seconds": values["cd_exec"] / 60.0,
            "ad_trans_seconds": values["ad_trans"] / 60.0,
            "ad_read_seconds": values["ad_read"] / 60.0,
            "ad_write_seconds": values["ad_write"] / 60.0,
            "fade_wait_seconds": values["fade_wait"] / 60.0,
            "residual_seconds": values["residual"] / 60.0,
            "known_serial_percent": known / total * 100.0,
            "residual_percent": values["residual"] / total * 100.0,
        })
    if not rows:
        raise ValueError("no TRANSITION_BUDGET rows found")
    return {
        "transition_count": len(rows),
        "transitions": rows,
        "caveat": (
            "Serial component frames are measured entry-to-return and should not "
            "be double-counted with higher-level wrappers. Residual time includes "
            "portrait/UI installation, initialization/display work, uninstrumented "
            "waits, and CPU-side setup between measured calls."
        ),
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Cyber City Oedo 808 transition budgets.")
    parser.add_argument("log", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    report = parse_transition_budgets(args.log.read_text(encoding="utf-8", errors="replace"))
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
