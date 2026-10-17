#!/usr/bin/env python3
"""Improve the gold H4 MACD strategy: one-change sweep, then combinations. Choose on Q4 2024 + 2025; 2026 = check.
    python scripts/macd_improve.py sweep|combo"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G, macd as M  # noqa: E402

OUT = ROOT / "results" / "macd"
SWEEP = {
    "tf": ["1h", "2h", "6h", "1D"], "fast": [8, 16], "slow": [21, 34], "signal": [5, 12], "trend": [0, 50, 200, 400],
    "zero_line": [True], "adx_min": [15.0, 20.0, 25.0], "d1_trend": [10, 20, 50], "stop_atr": [1.5, 2.0, 2.5, 4.0, 5.0],
    "rr": [1.5, 2.0, 3.0, 4.0, 6.0], "be": [0.5, 1.0, 1.5], "trail_atr": [2.0, 3.0, 4.0, 6.0],
    "exit_mode": ["ema", "none"], "reverse": [False],
}


def run(kw):
    kw2 = dict(kw)
    if kw2.get("trend") == 0:
        kw2["trend"] = 1                       # EMA(1) = close: filter off
    return {**{k: str(v) for k, v in kw.items()}, **G.stats(M.backtest(M.data(ROOT), M.P(**kw2)))}


COMBO = dict(tf=["2h", "3h", "4h"], trend=[100, 200], adx_min=[0.0, 15.0, 20.0], d1_trend=[0, 20],
             stop_atr=[2.0, 2.5, 3.0], rr=[0.0, 1.5, 3.0], trail_atr=[0.0, 4.0], reverse=[True, False])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    combo = sys.argv[1:] == ["combo"]
    if combo:
        jobs = [dict(zip(COMBO, v)) for v in itertools.product(*COMBO.values())]
    else:
        jobs = [{}] + [{k: v} for k, vals in SWEEP.items() for v in vals]
    with ProcessPoolExecutor(4) as ex:
        rows = list(ex.map(run, jobs, chunksize=4))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / ("combo.csv" if combo else "sweep.csv"), index=False)
    if not combo:
        keys = list(SWEEP)
        df["change"] = df[[k for k in keys if k in df]].apply(lambda r: ",".join(f"{k}={v}" for k, v in r.items() if isinstance(v, str)), axis=1)
        cols = ["change", "q4_24_n", "q4_24_pf", "y25_n", "y25_win", "y25_avg", "y25_pf", "y25_usd", "y25_dd",
                "y26_n", "y26_win", "y26_avg", "y26_pf", "y26_usd", "y26_dd"]
        print(df[cols].round(2).to_string(index=False))
    print(len(df), "runs")
