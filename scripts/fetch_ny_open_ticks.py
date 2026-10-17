#!/usr/bin/env python3
"""Download Dukascopy TICK data (bid/ask, ~7 ticks/s) for the two UTC hours
around every New York cash open (09:30 America/New_York) for Nasdaq and Dow.

Files are cached as data/ticks/<SYM>/<YYYY-MM-DD>_<HH>.npy (columns: ms from
the hour, ask, bid).  Polite: 2 threads, back-off on HTTP 429.  Dukascopy
throttles to roughly 0.2 files/s, so --hours 1 --newest-first is practical.

    python scripts/fetch_ny_open_ticks.py --start 2024-10-01 --end 2026-10-15
"""
from __future__ import annotations

import argparse
import lzma
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/{d:02d}/{h:02d}h_ticks.bi5"
SYMBOLS = {"USATECHIDXUSD": "NAS100", "USA30IDXUSD": "US30"}
SCALE = 1e3
NYSE_HOLIDAYS = {
    "2024-11-28", "2024-12-25", "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25", "2026-01-01",
    "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
}


def ny_open_utc(d: date) -> pd.Timestamp:
    return pd.Timestamp(f"{d} 09:30", tz="America/New_York").tz_convert("UTC").tz_localize(None)


def trading_days(a: date, b: date):
    d = a
    while d <= b:
        if d.weekday() < 5 and str(d) not in NYSE_HOLIDAYS:
            yield d
        d += timedelta(days=1)


def fetch(sess, sym, d, h, out: Path, scale: float = SCALE):
    if out.exists():
        return "cached"
    url = URL.format(sym=sym, y=d.year, m=d.month - 1, d=d.day, h=h)
    for attempt in range(10):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 429:
                time.sleep(3 + 3 * attempt)
                continue
            if r.status_code == 404:
                np.save(out, np.zeros((0, 3)))
                return "missing"
            r.raise_for_status()
            raw = lzma.decompress(r.content) if r.content else b""
            arr = np.array([(t, a / scale, b / scale) for t, a, b, _, _ in struct.iter_unpack(">IIIff", raw)])
            np.save(out, arr.reshape(-1, 3))
            time.sleep(0.3)
            return "ok"
        except (requests.RequestException, lzma.LZMAError):
            time.sleep(2 + 2 * attempt)
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-10-01")
    ap.add_argument("--end", default="2026-10-15")
    ap.add_argument("--hours", type=int, default=2, help="1 = only the hour containing the open")
    ap.add_argument("--newest-first", action="store_true")
    a = ap.parse_args()
    jobs = []
    for d in trading_days(date.fromisoformat(a.start), date.fromisoformat(a.end)):
        h0 = ny_open_utc(d).hour
        for sym, name in SYMBOLS.items():
            folder = ROOT / "data" / "ticks" / name
            folder.mkdir(parents=True, exist_ok=True)
            for h in (h0, h0 + 1)[:a.hours]:
                jobs.append((sym, d, h, folder / f"{d}_{h:02d}.npy"))
    if a.newest_first:
        jobs.reverse()
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (oncandle backtester)"
    done = {"ok": 0, "cached": 0, "missing": 0, "failed": 0}
    with ThreadPoolExecutor(2) as ex:
        for i, res in enumerate(ex.map(lambda j: fetch(s, *j), jobs)):
            done[res] += 1
            if i % 200 == 0:
                print(f"{i}/{len(jobs)} {done}", flush=True)
    print("finished", done, flush=True)
    if done["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
