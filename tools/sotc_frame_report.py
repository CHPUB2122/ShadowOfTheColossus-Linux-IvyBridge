#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read existing SOTCFRAME timing; never launch a game or change a save/cache.

Use run.sh --benchmark, keep the last scene/viewpoint fixed for 60+ seconds,
close normally, then pass its game.log and --last-seconds 60 to this script.
These are presentation intervals, not GPU execution times.
"""
import argparse
import json
from pathlib import Path
import re


def percentile(values, fraction):
    values = sorted(values)
    at = (len(values) - 1) * fraction
    low = int(at)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (at - low)


def report(text, last_seconds=60):
    frames = [(int(f), int(us)) for f, us in
              re.findall(r"^SOTCFRAME (\d+) t=\d+ms us=(\d+)\s*$", text, re.MULTILINE)]
    if len(frames) < 2:
        raise ValueError("need at least two SOTCFRAME timestamps; use run.sh --benchmark")
    cutoff = frames[-1][1] - last_seconds * 1_000_000
    intervals = [(f1-f0, t1-t0) for (f0, t0), (f1, t1) in zip(frames, frames[1:])
                 if t0 >= cutoff and f1 > f0 and t1 > t0]
    if not intervals:
        raise ValueError("no complete timing intervals in the requested window")
    count, us = map(sum, zip(*intervals))
    result = {"frames": count, "seconds": us / 1_000_000,
              "fps": count * 1_000_000 / us, "mean_frame_ms": us / count / 1000,
              "metric": "game presentation intervals; excludes generated/repeated frames",
              "requested_last_seconds": last_seconds,
              "note": "Scene, warmup, image correctness and GPU saturation are not established by this log."}
    if all(n == 1 for n, dt in intervals):
        ms = [dt / 1000 for n, dt in intervals]
        result.update(p50_ms=percentile(ms, .5), p95_ms=percentile(ms, .95),
                      p99_ms=percentile(ms, .99), worst_ms=max(ms))
    else:
        result["percentiles_unavailable"] = "timestamps are grouped; per-frame percentiles would be misleading"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--last-seconds", type=float, default=60)
    args = parser.parse_args()
    if args.last_seconds <= 0:
        parser.error("--last-seconds must be positive")
    try:
        print(json.dumps(report(args.log.read_text(errors="replace"), args.last_seconds), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, f"sotc: {error}\n")


if __name__ == "__main__":
    main()
