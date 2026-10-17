#!/usr/bin/env python3
"""Gold MACD v3: shorter losing streaks than v2 with at least v2's profit.
Engine variants (ADX, daily trend, break-even, partial profit, volatility cap, hours) x overlays (cool-down after k
losses until a paper trade wins; equity-curve filter). Chosen on Q4 2024 + 2025; 2026 is the check.
    python scripts/macd_v3.py   -> results/macd/v3_grid.csv"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G, macd as M  # noqa: E402

V2 = dict(tf="2h", trend=100, stop_atr=2.0, rr=3.0)
DAY = tuple(range(6, 22))
ENGINE = dict(adx_min=[0.0, 15.0, 20.0], d1_trend=[0, 20], be=[0.0, 1.0, 1.5], be_buf=[0.1, 0.5],
              partial=[0.0, 0.5], partial_r=[1.0, 1.5], vol_max=[99.0, 2.0], hours=[(), DAY])
OVER = dict(cool_k=[0, 3, 4, 5], eq_n=[0, 10])


def streak(r):
    best = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def overlay(t, cool_k, eq_n, eq_thr=-3.0):
    """cool_k: after cool_k real losses in a row, skip trades until a paper trade wins.
    eq_n: take a trade only if the last eq_n paper trades sum to >= eq_thr R."""
    r = t.r.to_numpy()
    take = np.ones(len(r), bool)
    run, paused = 0, False
    cs = np.r_[0.0, np.cumsum(r)]
    for i in range(len(r)):
        if eq_n and i >= eq_n and cs[i] - cs[i - eq_n] < eq_thr:
            take[i] = False
        if cool_k and paused:
            take[i] = False
        if take[i]:
            run = run + 1 if r[i] < 0 else 0
            if cool_k and run >= cool_k:
                paused, run = True, 0
        elif paused and r[i] > 0:
            paused = False                        # a paper win ends the pause (this trade itself was skipped)
    return t[take]


def job(ekw):
    if ekw["be"] == 0 and ekw["be_buf"] != 0.1:
        return []
    if ekw["partial"] == 0 and ekw["partial_r"] != 1.0:
        return []
    t = M.backtest(M.data(ROOT), M.P(**V2, **ekw))
    rows = []
    for v in itertools.product(*OVER.values()):
        okw = dict(zip(OVER, v))
        x = overlay(t, **okw)
        st = G.stats(x)
        for k, (a, b) in G.PERIODS.items():
            st[f"{k}_streak"] = streak(x[(x.entry_time >= a) & (x.entry_time < b)].r.to_numpy())
        st["all_streak"] = streak(x.r.to_numpy())
        rows.append({**{k: str(v) for k, v in ekw.items()}, **okw, **st})
    return rows


if __name__ == "__main__":
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    with ProcessPoolExecutor(4) as ex:
        rows = [r for rs in ex.map(job, jobs, chunksize=2) for r in rs]
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "macd" / "v3_grid.csv", index=False)
    print(len(df), "variants")
