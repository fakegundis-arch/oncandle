#!/usr/bin/env python3
"""Download Dukascopy ticks around every high-impact USD data release.

Reads data/calendar/usd_high_impact_times.csv (built from the Forex Factory
calendar), drops speeches / press conferences, and fetches the UTC hour that
contains each release (plus the previous hour when the release is on the
hour, so the quote seconds before it is available).

    python scripts/fetch_news_ticks.py --markets XAUUSD NAS100 US30 EURUSD
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_ny_open_ticks import fetch  # noqa: E402

DUKA = {"XAUUSD": ("XAUUSD", 1e3), "NAS100": ("USATECHIDXUSD", 1e3), "US30": ("USA30IDXUSD", 1e3),
        "EURUSD": ("EURUSD", 1e5), "USDJPY": ("USDJPY", 1e3), "GBPUSD": ("GBPUSD", 1e5)}
NOT_A_RELEASE = ("Speaks", "Press Conference", "Testifies", "Speech")


def release_times(end="2026-10-15 23:59") -> pd.DataFrame:
    g = pd.read_csv(ROOT / "data" / "calendar" / "usd_high_impact_times.csv", parse_dates=["time_utc"])
    names = g.name.str.split(" \\+ ")
    keep = names.apply(lambda ns: any(not any(w in n for w in NOT_A_RELEASE) for n in ns))
    g = g[keep & (g.time_utc <= end)].copy()
    g["name"] = names[keep].apply(lambda ns: " + ".join(n for n in ns if not any(w in n for w in NOT_A_RELEASE)))
    return g.reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", nargs="+", default=["XAUUSD", "NAS100", "US30", "EURUSD"])
    a = ap.parse_args()
    ev = release_times()
    jobs = []
    for t in ev.time_utc.sort_values(ascending=False):
        hours = [t.floor("h")]
        if t.minute == 0:
            hours.insert(0, t.floor("h") - pd.Timedelta("1h"))
        for m in a.markets:
            sym, scale = DUKA[m]
            folder = ROOT / "data" / "ticks" / m
            folder.mkdir(parents=True, exist_ok=True)
            for h in hours:
                jobs.append((sym, h.date(), h.hour, folder / f"{h.date()}_{h.hour:02d}.npy", scale))
    print(len(ev), "releases,", len(jobs), "tick files", flush=True)
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (oncandle backtester)"
    done = {"ok": 0, "cached": 0, "missing": 0, "failed": 0}
    with ThreadPoolExecutor(2) as ex:
        for i, res in enumerate(ex.map(lambda j: fetch(s, *j), jobs)):
            done[res] += 1
            if i % 100 == 0:
                print(f"{i}/{len(jobs)} {done}", flush=True)
    print("finished", done, flush=True)


if __name__ == "__main__":
    main()
