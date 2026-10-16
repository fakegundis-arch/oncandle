#!/usr/bin/env python3
"""Download free historical H1 BID candles from Dukascopy and save them as
data/<SYMBOL>_H1.csv.

    python scripts/fetch_dukascopy.py EURUSD GBPUSD USDJPY --start 2005 --end 2026

Dukascopy stores one LZMA-compressed .bi5 file of hourly candles per month:
    https://datafeed.dukascopy.com/datafeed/EURUSD/2020/00/BID_candles_hour_1.bi5
(months are 0-based).  Each record is 24 bytes, big-endian:
    uint32 seconds-from-month-start, uint32 open, close, low, high, float32 volume
with prices stored as integers (x 1e5, or x 1e3 for JPY pairs and metals).
"""
from __future__ import annotations

import argparse
import lzma
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{y}/{m:02d}/BID_candles_hour_1.bi5"
DEFAULT = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
           "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "XAUUSD"]


def scale(sym: str) -> float:
    return 1e3 if ("JPY" in sym or sym.startswith("XA")) else 1e5


def fetch_month(sym: str, y: int, m: int, session: requests.Session) -> list[tuple]:
    url = URL.format(sym=sym, y=y, m=m - 1)
    for attempt in range(5):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            break
        except requests.RequestException:
            time.sleep(2 ** attempt)
    else:
        print(f"  ! failed {url}", file=sys.stderr)
        return []
    if not r.content:
        return []
    raw = lzma.decompress(r.content)
    base = datetime(y, m, 1, tzinfo=timezone.utc).timestamp()
    k = scale(sym)
    rows = []
    for t, o, c, lo, hi, v in struct.iter_unpack(">IIIIIf", raw):
        rows.append((base + t, o / k, hi / k, lo / k, c / k, v))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=DEFAULT)
    ap.add_argument("--start", type=int, default=2005)
    ap.add_argument("--end", type=int, default=datetime.now(timezone.utc).year)
    ap.add_argument("--out", default=str(ROOT / "data"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    months = [(y, m) for y in range(a.start, a.end + 1) for m in range(1, 13)
              if (y, m) < (now.year, now.month)]
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (oncandle backtester)"
    for sym in a.symbols:
        sym = sym.upper()
        with ThreadPoolExecutor(8) as ex:
            parts = list(ex.map(lambda ym: fetch_month(sym, *ym, s), months))
        rows = [r for p in parts for r in p]
        if not rows:
            print(f"{sym}: no data")
            continue
        df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df[df.volume > 0].drop_duplicates("time").sort_values("time")
        bad = (df.low > df[["open", "close"]].min(axis=1)) | (df.high < df[["open", "close"]].max(axis=1))
        if bad.mean() > 0.01:
            print(f"{sym}: {bad.mean():.1%} inconsistent bars - check record layout", file=sys.stderr)
        path = out / f"{sym}_H1.csv"
        df.to_csv(path, index=False)
        print(f"{sym}: {len(df):,} bars {df.time.iloc[0]:%Y-%m-%d} -> {df.time.iloc[-1]:%Y-%m-%d}  -> {path}")


if __name__ == "__main__":
    main()
