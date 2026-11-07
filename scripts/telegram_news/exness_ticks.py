"""Exness tick history (ticks.ex2archive.com, the broker's own monthly bid / ask files) -> one-second bars.

For every second with at least one tick: first / last / min / max of bid and of ask, and the tick count.  Saved as
data/ticks_exness/<SYMBOL>/<YYYY-MM>.npz (t = unix seconds, int64; prices float64).  The raw zip is deleted.

usage: python3 -I scripts/telegram_news/exness_ticks.py <SYMBOL> <YYYY-MM> <YYYY-MM> <workdir>
       e.g. XAUUSDm 2026-01 2026-10 /tmp/work"""
import io
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
URL = "https://ticks.ex2archive.com/ticks/{s}/{y}/{m:02d}/Exness_{s}_{y}_{m:02d}.zip"


def months(a: str, b: str):
    y, m = map(int, a.split("-"))
    y2, m2 = map(int, b.split("-"))
    while (y, m) <= (y2, m2):
        yield y, m
        y, m = (y + (m == 12), m % 12 + 1)


def fetch(url: str, dst: Path):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=600) as r, \
                    open(dst, "wb") as fh:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    fh.write(b)
            return
        except Exception as ex:                                  # noqa: BLE001
            print("  retry", i, ex, flush=True)
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"download failed: {url}")


def convert(zpath: Path) -> dict:
    parts = []
    with zipfile.ZipFile(zpath) as z:
        name = z.namelist()[0]
        with z.open(name) as fh:
            for ch in pd.read_csv(io.TextIOWrapper(fh), usecols=["Timestamp", "Bid", "Ask"], chunksize=2_000_000):
                ts = pd.to_datetime(ch.Timestamp.str.slice(0, 23), format="%Y-%m-%d %H:%M:%S.%f")   # UTC, naive
                sec = ts.to_numpy().astype("datetime64[s]").astype(np.int64)
                d = pd.DataFrame({"s": sec, "bid": ch.Bid.to_numpy(float), "ask": ch.Ask.to_numpy(float)})
                parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    g = d.groupby("s", sort=True)
    a = g.agg(bid_first=("bid", "first"), bid_last=("bid", "last"), bid_min=("bid", "min"), bid_max=("bid", "max"),
              ask_first=("ask", "first"), ask_last=("ask", "last"), ask_min=("ask", "min"), ask_max=("ask", "max"),
              n=("bid", "size"))
    out = {"t": a.index.to_numpy(np.int64)}
    for c in a.columns:
        out[c] = a[c].to_numpy(np.float64 if c != "n" else np.int32)
    return out


def main():
    sym, a, b, work = sys.argv[1], sys.argv[2], sys.argv[3], Path(sys.argv[4])
    work.mkdir(parents=True, exist_ok=True)
    out_dir = ROOT / "data/ticks_exness" / sym
    out_dir.mkdir(parents=True, exist_ok=True)
    for y, m in months(a, b):
        out = out_dir / f"{y}-{m:02d}.npz"
        if out.exists():
            print(sym, y, m, "exists", flush=True)
            continue
        z = work / f"{sym}_{y}_{m:02d}.zip"
        t0 = time.time()
        fetch(URL.format(s=sym, y=y, m=m), z)
        arr = convert(z)
        np.savez_compressed(out, **arr)
        z.unlink()
        print(f"{sym} {y}-{m:02d}: {len(arr['t'])} seconds with ticks, {arr['n'].sum()} ticks, "
              f"median spread {np.median(arr['ask_last'] - arr['bid_last']):.3f} ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
