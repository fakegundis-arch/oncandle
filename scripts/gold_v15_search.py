#!/usr/bin/env python3
"""Gold Asian breakout v15 search: v13 (Asia 00-06 + New York 12-15 engines, v10 filters) with drawdown controls,
ONE rule set for every month, every trade charged Dukascopy's recorded spread at its entry minute.

Shared by both engines: break-even, target, stop for the day after a loss, spread guard, minimum volatility, a graded
equity-curve filter (full risk / half risk / pause by the engine's last N paper trades) and the weekly stop;
booked for several risk splits. Chosen on 2026 only (rule in scripts/gold_v15.py); 2025 and Q4 2024 are the test.
    python scripts/gold_v15_search.py  -> results/gold/v15_search.parquet
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from backtester.engine import njit  # noqa: E402
from gold_versions import NY, V10, book  # noqa: E402

GRID = dict(be=[1.0, 1.5], be_buf=[0.3, 0.5], rr=[3.0, 4.0, 5.0], stop_after_loss=[False, True],
            min_stop_spread=[0.0, 8.0, 12.0, 16.0], atr_pct_min=[0.0, 0.08, 0.10])
OVER = dict(eq_n=[10, 20], eq_off=[-3.0, -2.0], eq_half=["none", "0"], week_cap=[0.0, -2.0])
RISK = dict(w_asia=[0.06, 0.08, 0.10, 0.12, 0.14], w_ny=[0.0, 0.02, 0.04])
PER = {"y26": ("2026-01-01", "2026-11-01"), "y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}
COST = dict(cost_mode="data")


@njit(cache=True)
def graded(r, week, eq_n, eq_off, eq_half, week_cap):
    """Risk multiplier per trade from the engine's own paper trades (all signals): 0 = skip (last eq_n paper trades sum
    below eq_off, or this week's real trades are already at week_cap R), 0.5 = between eq_off and eq_half, 1 = full."""
    n = len(r)
    mult = np.ones(n)
    s = 0.0
    for i in range(n):
        if eq_n > 0 and i >= eq_n:
            if s < eq_off:
                mult[i] = 0.0
            elif s < eq_half:
                mult[i] = 0.5
        s += r[i]
        if eq_n > 0 and i >= eq_n:
            s -= r[i - eq_n]
    if week_cap < 0:
        cur = -1
        run = 0.0
        for i in range(n):
            if week[i] != cur:
                cur = week[i]
                run = 0.0
            if run <= week_cap:
                mult[i] = 0.0
            elif mult[i] > 0:
                run += r[i] * mult[i]
    return mult


def apply(t, eq_n, eq_off, eq_half, week_cap):
    iso = t.entry_time.dt.isocalendar()
    week = (iso.year * 100 + iso.week).to_numpy(np.int64)
    half = eq_off if eq_half == "none" else float(eq_half)
    m = graded(t.r.to_numpy(np.float64), week, eq_n, eq_off, half, week_cap)
    return t.assign(mult=m)[m > 0]


def job(kw):
    m1, m15 = G.data(ROOT)
    ch = {**kw, **COST}
    a0 = G.backtest(m1, m15, replace(V10, **ch))
    n0 = G.backtest(m1, m15, replace(NY, **ch))
    rows = []
    for ov in itertools.product(*OVER.values()):
        o = dict(zip(OVER, ov))
        a, n = apply(a0, **o), apply(n0, **o)
        for wa, wn in itertools.product(*RISK.values()):
            t = pd.concat([a.assign(f=wa * a.mult)] + ([n.assign(f=wn * n.mult)] if wn > 0 else []))
            r = {**kw, **o, "w_asia": wa, "w_ny": wn}
            for k, (s, e) in PER.items():
                usd, dd, rets, cnt = book(t, s, e)
                r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": int((rets > 0).sum()), f"{k}_m": len(rets),
                          f"{k}_worst": float(rets.min()), f"{k}_n": cnt})
            rows.append(r)
    df = pd.DataFrame(rows)
    for c in df.select_dtypes("float64"):
        if c.endswith(("_usd", "_dd", "_worst")):
            df[c] = df[c].astype("float32")
    return df


def main():
    jobs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, jobs, chunksize=2)):
            parts.append(df)
            if i % 24 == 0:
                print(i, "/", len(jobs), flush=True)
    pd.concat(parts, ignore_index=True).to_parquet(ROOT / "results/gold/v15_search.parquet", index=False)
    print(sum(len(p) for p in parts), "combinations")


if __name__ == "__main__":
    main()
