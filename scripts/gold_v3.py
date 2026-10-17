#!/usr/bin/env python3
"""Gold Asian breakout v3: drawdown control on top of v2.  Engine-level filters (volatility regime, daily limits)
plus trade-list overlays (equity-curve filter, weekly loss cap).  Chosen on Q4 2024 + 2025; 2026 is the check.

    python scripts/gold_v3.py        # -> results/gold/v3_grid.csv
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G  # noqa: E402

V2 = dict(don=20, rr=4.0, slope=16, stop_atr=1.5, be_buf=0.3)
ENGINE = dict(regime_max=[99.0, 1.6, 1.4, 1.25], stop_after_loss=[False, True], max_per_day=[99, 2, 1],
              vol_max=[99.0, 2.0], d1_trend=[0, 20])
OVERLAY = dict(eq_n=[0, 5, 10, 20], eq_thr=[-2.0, 0.0], week_cap=[0.0, -2.0, -3.0])
RISK = 0.10


def overlay(t: pd.DataFrame, eq_n: int, eq_thr: float, week_cap: float) -> pd.DataFrame:
    """Equity-curve filter: take a trade only if the sum of the last eq_n *paper* trades (all signals) >= eq_thr.
    Weekly cap: after the real trades of an ISO week lose week_cap R, skip the rest of that week."""
    r = t.r.to_numpy()
    take = np.ones(len(t), bool)
    if eq_n > 0:
        cs = np.concatenate([[0.0], np.cumsum(r)])
        for i in range(len(r)):
            if i >= eq_n and cs[i] - cs[i - eq_n] < eq_thr:
                take[i] = False
    if week_cap < 0:
        wk = t.entry_time.dt.isocalendar()
        key = (wk.year * 100 + wk.week).to_numpy()
        run, cur = 0.0, None
        for i in range(len(r)):
            if key[i] != cur:
                cur, run = key[i], 0.0
            if run <= week_cap:
                take[i] = False
            elif take[i]:
                run += r[i]
    return t[take]


def score(t):
    out = G.stats(t, RISK)
    return out


def job(ekw):
    m1, m15 = G.data(ROOT)
    t = G.backtest(m1, m15, G.P(**V2, **ekw))
    rows = []
    for v in itertools.product(*OVERLAY.values()):
        okw = dict(zip(OVERLAY, v))
        if okw["eq_n"] == 0 and okw["eq_thr"] != OVERLAY["eq_thr"][0]:
            continue
        rows.append({**ekw, **okw, **score(overlay(t, **okw))})
    return rows


def main():
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    with ProcessPoolExecutor(4) as ex:
        rows = [r for rs in ex.map(job, jobs) for r in rs]
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "gold" / "v3_grid.csv", index=False)
    print(len(df), "variants")


if __name__ == "__main__":
    main()
