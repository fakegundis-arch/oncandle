#!/usr/bin/env python3
"""Download M1 BID + ASK candles from Dukascopy for BTC, gold, Dow and
Nasdaq and save data/<SYMBOL>_M1.csv with a per-bar `spread` column
(ask close - bid close), which the backtests charge as trading cost.

    python scripts/fetch_dukascopy_m1.py --start 2024-10-01 --end 2026-10-15

Files are one LZMA .bi5 per day:
    https://datafeed.dukascopy.com/datafeed/XAUUSD/2025/08/15/BID_candles_min_1.bi5
(month is 0-based).  Record: >IIIIIf = seconds-from-midnight, open, close,
low, high (integers / scale), volume.
"""
from __future__ import annotations

import argparse
import lzma
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://datafeed.dukascopy.com/datafeed/{sym}/{d.year}/{m:02d}/{d.day:02d}/{side}_candles_min_1.bi5"
# dukascopy name -> (our name, price scale)
SYMBOLS = {
    "BTCUSD": ("BTCUSD", 10.0),
    "XAUUSD": ("XAUUSD", 1e3),
    "USATECHIDXUSD": ("NAS100", 1e3),
    "USA30IDXUSD": ("US30", 1e3),
    "USA500IDXUSD": ("US500", 1e3),
    "XAGUSD": ("XAGUSD", 1e3),
    "LIGHTCMDUSD": ("USOIL", 1e3),
    "EURUSD": ("EURUSD", 1e5),
    "GBPUSD": ("GBPUSD", 1e5),
    "USDJPY": ("USDJPY", 1e3),
    "USDCAD": ("USDCAD", 1e5),
}


def fetch_day(sym: str, scale: float, d: date, side: str, session: requests.Session):
    url = URL.format(sym=sym, d=d, m=d.month - 1, side=side)
    for attempt in range(6):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return []
            r.raise_for_status()
            break
        except requests.RequestException:
            time.sleep(1.5 * 2 ** attempt)
    else:
        print(f"  ! failed {url}", file=sys.stderr)
        return None
    if not r.content:
        return []
    base = datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()
    return [(base + t, o / scale, h / scale, lo / scale, c / scale, v)
            for t, o, c, lo, h, v in struct.iter_unpack(">IIIIIf", lzma.decompress(r.content))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", default=list(SYMBOLS))
    ap.add_argument("--start", default="2024-10-01")
    ap.add_argument("--end", default=str(date.today() - timedelta(days=1)))
    ap.add_argument("--out", default=str(ROOT / "data"))
    ap.add_argument("--threads", type=int, default=12)
    ap.add_argument("--bid-only", action="store_true", help="skip ASK candles (spread column = NaN)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    d0, d1 = date.fromisoformat(a.start), date.fromisoformat(a.end)
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (oncandle backtester)"
    cols = ["time", "open", "high", "low", "close", "volume"]

    for sym in a.symbols:
        name, scale = SYMBOLS[sym]
        frames = {}
        for side in (("BID",) if a.bid_only else ("BID", "ASK")):
            with ThreadPoolExecutor(a.threads) as ex:
                parts = list(ex.map(lambda d: fetch_day(sym, scale, d, side, s), days))
            failed = sum(p is None for p in parts)
            rows = [r for p in parts if p for r in p]
            df = pd.DataFrame(rows, columns=cols)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            frames[side] = df.set_index("time")
            print(f"{name} {side}: {len(df):,} rows, {failed} days failed")
        bid = frames["BID"]
        bid = bid[bid.volume > 0].copy()
        if "ASK" in frames:
            bid["spread"] = (frames["ASK"]["close"] - bid["close"]).reindex(bid.index)
            bid["spread"] = bid["spread"].clip(lower=0).fillna(bid["spread"].median())
        else:
            bid["spread"] = np.nan
        path = out / f"{name}_M1.csv"
        bid[["open", "high", "low", "close", "spread"]].to_csv(path)
        print(f"{name}: {len(bid):,} bars {bid.index[0]} -> {bid.index[-1]}, "
              f"median spread {bid.spread.median():g} -> {path}")


if __name__ == "__main__":
    main()
