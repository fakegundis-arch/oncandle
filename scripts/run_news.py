#!/usr/bin/env python3
"""Backtest the two news setups on every high-impact USD release with ticks.

    python scripts/run_news.py            # uses whatever tick files are cached

Distances are multiples of each market's "news unit" = median first-minute
range (mid price) over the previous 10 releases with data - known before the
event.  A: 10% risk per trade.  B: 5% per position (10% if both are stopped).
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import news as N  # noqa: E402
from fetch_news_ticks import release_times  # noqa: E402

MARKETS = ["XAUUSD", "NAS100", "US30", "EURUSD"]
A_GRID = dict(dist=(0.1, 0.25, 0.5), sl=(0.25, 0.5, 1.0), rr=(2.0, 3.0, 4.0), pre_s=(10, 60), expiry_s=(60, 300))
B_GRID = dict(sl=(0.25, 0.5, 1.0, 1.5), rr=(3.0, 4.0, 5.0))


def grow(r, risk):
    eq = np.cumprod(np.maximum(1 + risk * np.asarray(r), 0))
    return (eq[-1], (eq / np.maximum.accumulate(eq) - 1).min()) if len(eq) else (1.0, 0.0)


def stats(df, risk):
    out = {}
    for k, (a, b) in {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01"),
                      "all": ("2000", "2100")}.items():
        x = df[(df.time >= a) & (df.time < b)]
        r = x.r.to_numpy()
        if not len(r):
            continue
        m, dd = grow(r, risk)
        loss = -r[r < 0].sum()
        out.update({f"{k}_n": len(r), f"{k}_win": (r > 0).mean(), f"{k}_avg_r": r.mean(),
                    f"{k}_pf": r[r > 0].sum() / loss if loss > 0 else np.inf, f"{k}_usd": 1000 * m, f"{k}_dd": dd})
    return out


def main():
    ev = release_times()
    rows_a, rows_b, units_log = [], [], []
    for m in MARKETS:
        data, rng = [], []
        for _, e in ev.sort_values("time_utc").iterrows():
            x = N.load_ticks(m, e.time_utc)
            if x is None:
                continue
            fr = N.first_minute_range(*x)
            unit = np.nanmedian(rng[-10:]) if len(rng) >= 5 else np.nan
            rng.append(fr)
            if np.isfinite(unit):
                data.append((e.time_utc, e["name"], x, unit))
        if not data:
            print("no tick data for", m)
            continue
        units_log.append((m, len(data), np.median([u for *_, u in data])))
        for dist, sl, rr, pre, exp in itertools.product(*A_GRID.values()):
            res = []
            for t, name, (ms, ask, bid), u in data:
                r = N.straddle(ms, ask, bid, N.Straddle(dist=dist * u, sl=sl * u, rr=rr, pre_s=pre, expiry_s=exp))
                if r:
                    res.append({"time": t, "event": name, **r})
            df = pd.DataFrame(res)
            if len(df):
                rows_a.append({"market": m, "dist_u": dist, "sl_u": sl, "rr": rr, "pre_s": pre, "expiry_s": exp,
                               "events": len(data), **stats(df, 0.10)})
        for sl, rr in itertools.product(*B_GRID.values()):
            res = []
            for t, name, (ms, ask, bid), u in data:
                r = N.double(ms, ask, bid, N.Double(sl=sl * u, rr=rr))
                if r:
                    res.append({"time": t, "event": name, **r})
            df = pd.DataFrame(res)
            if len(df):
                rows_b.append({"market": m, "sl_u": sl, "rr": rr, "events": len(data), **stats(df, 0.05)})
        print(f"done {m}: {len(data)} releases with ticks", flush=True)
    out = ROOT / "results" / "news"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows_a).to_csv(out / "straddle_grid.csv", index=False)
    pd.DataFrame(rows_b).to_csv(out / "double_grid.csv", index=False)
    print("news units (median first-minute range):", units_log)


if __name__ == "__main__":
    main()
