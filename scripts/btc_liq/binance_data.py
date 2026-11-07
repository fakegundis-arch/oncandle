"""Binance USD-M BTCUSDT public data (data.binance.vision) -> compact local files under data/btc/.

  aggtrades : every aggregated trade -> one-second bars: open / high / low / close price, taker-BUY and taker-SELL
              quantity (BTC), number of aggressive buy / sell trades, largest single aggressive buy / sell trade.
              -> data/btc/binance_1s/<YYYY-MM>.npz      (forced liquidations are executed as aggressive market orders)
  metrics   : 5-minute open interest, long / short ratios, taker volume ratio -> data/btc/metrics.csv.gz
  bookdepth : order-book depth at +/-0.2 %, 1 %, 2 %, 3 %, 4 %, 5 % from the price, about every 30 s
              -> data/btc/bookdepth/<YYYY-MM>.parquet

usage: python3 -I scripts/btc_liq/binance_data.py <aggtrades|metrics|bookdepth> <YYYY-MM-DD> <YYYY-MM-DD>"""
import io
import sys
import time
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "btc"
BASE = "https://data.binance.vision/data/futures/um/daily/{kind}/BTCUSDT/BTCUSDT-{kind}-{d}.zip"


def get(url: str) -> bytes | None:
    for i in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** i)
        except Exception:
            time.sleep(2 ** i)
    raise RuntimeError("download failed: " + url)


def read_csv(blob: bytes, **kw) -> pd.DataFrame:
    z = zipfile.ZipFile(io.BytesIO(blob))
    with z.open(z.namelist()[0]) as fh:
        raw = fh.read()
    first = raw[:200].decode(errors="ignore").split("\n")[0]
    has_header = any(c.isalpha() for c in first.replace("true", "").replace("false", ""))
    return pd.read_csv(io.BytesIO(raw), header=0 if has_header else None, **kw)


def days(a: str, b: str):
    d, e = date.fromisoformat(a), date.fromisoformat(b)
    while d <= e:
        yield d
        d += timedelta(days=1)


def bars_1s(df: pd.DataFrame) -> dict:
    t = (df.transact_time.to_numpy(np.int64) // 1000)
    px = df.price.to_numpy(np.float64)
    q = df.quantity.to_numpy(np.float64)
    sell = df.is_buyer_maker.to_numpy(bool)          # buyer is maker -> the aggressor SOLD
    o = np.argsort(t, kind="stable")
    t, px, q, sell = t[o], px[o], q[o], sell[o]
    u, start = np.unique(t, return_index=True)
    end = np.r_[start[1:], len(t)]
    qb, qs = np.where(sell, 0.0, q), np.where(sell, q, 0.0)
    red = lambda f, x: f.reduceat(x, start)
    return dict(t=u, o=px[start], c=px[end - 1], h=red(np.maximum, px), l=red(np.minimum, px),
                bq=red(np.add, qb).astype(np.float32), sq=red(np.add, qs).astype(np.float32),
                nb=red(np.add, (~sell).astype(np.int32)), ns=red(np.add, sell.astype(np.int32)),
                mb=red(np.maximum, qb).astype(np.float32), ms=red(np.maximum, qs).astype(np.float32))


def aggtrades(a: str, b: str):
    (OUT / "binance_1s").mkdir(parents=True, exist_ok=True)
    month, parts = None, []

    def flush():
        if parts:
            m = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
            f = OUT / "binance_1s" / f"{month}.npz"
            if f.exists():                                 # merge with days already saved for this month
                old = dict(np.load(f))
                m = {k: np.concatenate([old[k], m[k]]) for k in m}
                o = np.argsort(m["t"], kind="stable")
                keep = np.r_[True, np.diff(m["t"][o]) > 0]
                m = {k: v[o][keep] for k, v in m.items()}
            np.savez_compressed(f, **m)
            print("saved", f, len(m["t"]), flush=True)

    for d in days(a, b):
        if d.strftime("%Y-%m") != month:
            flush()
            month, parts = d.strftime("%Y-%m"), []
        blob = get(BASE.format(kind="aggTrades", d=d.isoformat()))
        if blob is None:
            print("missing", d, flush=True)
            continue
        df = read_csv(blob, names=None)
        if "transact_time" not in df.columns:
            df.columns = ["agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id", "transact_time",
                          "is_buyer_maker"][: len(df.columns)]
        if df.is_buyer_maker.dtype != bool:
            df["is_buyer_maker"] = df.is_buyer_maker.astype(str).str.lower().eq("true")
        parts.append(bars_1s(df))
        print(d, len(df), "trades ->", len(parts[-1]["t"]), "s", flush=True)
    flush()


def metrics(a: str, b: str):
    rows = []
    for d in days(a, b):
        blob = get(BASE.format(kind="metrics", d=d.isoformat()))
        if blob is not None:
            rows.append(read_csv(blob))
    df = pd.concat(rows).drop_duplicates("create_time").sort_values("create_time")
    f = OUT / "metrics.csv.gz"
    if f.exists():
        df = pd.concat([pd.read_csv(f), df]).drop_duplicates("create_time").sort_values("create_time")
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(f, index=False)
    print("metrics rows", len(df), df.create_time.min(), df.create_time.max())


def bookdepth(a: str, b: str):
    (OUT / "bookdepth").mkdir(parents=True, exist_ok=True)
    by_month: dict = {}
    for d in days(a, b):
        blob = get(BASE.format(kind="bookDepth", d=d.isoformat()))
        if blob is None:
            print("missing", d, flush=True)
            continue
        df = read_csv(blob)
        w = df.pivot_table(index="timestamp", columns="percentage", values="depth", aggfunc="last")
        w.columns = [f"d{c:+.1f}" for c in w.columns]
        w.index = pd.to_datetime(w.index)
        by_month.setdefault(d.strftime("%Y-%m"), []).append(w)
    for m, ws in by_month.items():
        w = pd.concat(ws).sort_index()
        w = w[~w.index.duplicated()]
        w.reset_index().rename(columns={"timestamp": "time"}).to_parquet(OUT / "bookdepth" / f"{m}.parquet")
        print("bookdepth", m, len(w))


if __name__ == "__main__":
    {"aggtrades": aggtrades, "metrics": metrics, "bookdepth": bookdepth}[sys.argv[1]](sys.argv[2], sys.argv[3])
