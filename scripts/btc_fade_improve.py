#!/usr/bin/env python3
"""Improve the BTC H1 Run Fade: one-change sweeps, then combinations. Choose on Q4 2024 + 2025; 2026 is the check.
    python scripts/btc_fade_improve.py sweep|combo"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import btcfade as B, gold as G  # noqa: E402

OUT = ROOT / "results" / "btc"
SWEEP = {
    "tf": ["30min", "2h", "4h"], "run_len": [3, 5, 6], "min_move": [1.5, 2.0, 3.0, 3.5, 4.0], "max_move": [4.0, 5.0, 6.0],
    "tp": [0.3, 0.75, 1.0, 1.5, 2.0], "sl": [2.0, 3.0, 5.0, 6.0], "max_bars": [6, 12, 48, 96], "confirm": [True],
    "trend_ema": [50, 200, -50, -200], "side": [1, -1], "skip_weekend": [True],
    "hours": [tuple(range(0, 8)), tuple(range(8, 16)), tuple(range(13, 21)), tuple(range(16, 24))],
    "vol_max": [1.5, 2.0], "vol_min": [0.8, 1.0], "be": [0.5, 1.0], "trail": [1.0, 2.0], "max_per_day": [1, 2],
}


def run(kw):
    m1 = B.data(ROOT)
    return {**{k: str(v) for k, v in kw.items()}, **G.stats(B.backtest(m1, B.P(**kw)))}


def sweep():
    jobs = [{}] + [{k: v} for k, vals in SWEEP.items() for v in vals]
    with ProcessPoolExecutor(4) as ex:
        rows = list(ex.map(run, jobs))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "sweep.csv", index=False)
    return df


COMBO = dict(tf=["1h", "2h"], run_len=[3, 4, 5], min_move=[2.0, 2.5, 3.0], tp=[0.5, 0.75, 1.0], sl=[3.0, 4.0, 5.0],
             max_bars=[30, 48], trend_ema=[0, -50, -200], vol_max=[99.0, 1.5])


def combo():
    jobs = [dict(zip(COMBO, v)) for v in itertools.product(*COMBO.values())]
    with ProcessPoolExecutor(4) as ex:
        rows = list(ex.map(run, jobs, chunksize=8))
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
    d["change"] = d.drop(columns=[c for c in d.columns if "_" in c and c.split("_")[0] in ("q4", "y25", "y26")]).astype(str).agg(
        lambda r: ",".join(f"{k}={v}" for k, v in r.items() if v != "nan"), axis=1)
    cols = ["change", "q4_24_n", "q4_24_pf", "y25_n", "y25_win", "y25_avg", "y25_pf", "y25_usd", "y26_n", "y26_win",
            "y26_avg", "y26_pf", "y26_usd", "y26_dd"]
    print(d[cols].round(3).to_string(index=False))
