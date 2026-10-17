#!/usr/bin/env python3
"""Improve the gold Asian breakout: one-change-at-a-time sweeps around the baseline, then combinations.
Choose on 2025 (+ Q4 2024); 2026 is the check.   python scripts/gold_improve.py sweep|combo"""
from __future__ import annotations

import itertools
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G  # noqa: E402

OUT = ROOT / "results" / "gold"
SWEEP = {
    "ses_start": [22, 23, 0, 1], "ses_end": [3, 4, 5, 6, 7, 8, 10],
    "don": [5, 10, 15, 20, 30], "ema": [100, 200, 400, 800], "slope": [1, 4, 8, 16],
    "prev_day": [True, False], "donchian": [True, False], "asian_range": [0, 30, 60],
    "side": [0, 1, -1], "d1_trend": [0, 10, 20, 50], "vol_min": [0.0, 0.7, 0.9, 1.1], "vol_max": [99.0, 2.0, 1.5],
    "strong_close": [0.0, 0.3, 0.5],
    "stop_atr": [1.0, 1.25, 1.5, 2.0, 2.5, 3.0], "min_stop": [2.0, 4.0, 6.0], "rr": [1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    "be": [0.0, 0.5, 0.75, 1.0, 1.5], "be_buf": [0.0, 0.1, 0.3, 0.5], "trail_atr": [0.0, 1.0, 2.0, 3.0],
    "partial": [0.0, 0.33, 0.5], "partial_r": [1.0, 1.5, 2.0], "exit_hour": [-1, 8, 12, 16, 20],
    "max_hold_h": [0.0, 4.0, 8.0, 24.0], "max_per_day": [1, 2, 3, 99], "stop_after_loss": [False, True],
}


def run(p):
    m1, m15 = G.data(ROOT)
    return G.stats(G.backtest(m1, m15, p))


def sweep():
    base = G.P()
    rows = [{"param": "baseline", "value": "", **run(base)}]
    for k, vals in SWEEP.items():
        for v in vals:
            if getattr(base, k) == v:
                continue
            rows.append({"param": k, "value": v, **run(replace(base, **{k: v}))})
        print(k, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "sweep.csv", index=False)
    return df


COMBO = dict(stop_after_loss=[False, True], max_per_day=[1, 2, 99], d1_trend=[0, 10, 20], be_buf=[0.1, 0.3],
             slope=[4, 16], don=[10, 15, 20], rr=[2.5, 3.0, 4.0], stop_atr=[1.5, 2.0], asian_range=[0, 60],
             vol_min=[0.0, 0.7])


def _combo_job(kw):
    return {**kw, **run(G.P(**kw))}


def combo():
    from concurrent.futures import ProcessPoolExecutor
    jobs = [dict(zip(COMBO, v)) for v in itertools.product(*COMBO.values())]
    with ProcessPoolExecutor(4) as ex:
        rows = list(ex.map(_combo_job, jobs, chunksize=16))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "combo.csv", index=False)
    print(len(df), "combinations")
    return df


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    if sys.argv[1:] == ["combo"]:
        combo()
        sys.exit()
    d = sweep()
    cols = ["param", "value", "q4_24_pf", "q4_24_usd", "y25_n", "y25_pf", "y25_usd", "y25_dd", "y26_n", "y26_pf", "y26_usd", "y26_dd"]
    print(d[cols].round(2).to_string(index=False))

