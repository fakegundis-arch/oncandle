#!/usr/bin/env python3
"""BTC Run Fade: risk-reward sweep on the v2 signals (stop size x RR x break-even x hold).
Chosen on Q4 2024 + 2025; 2026 is the check.   python scripts/btc_fade_rr.py  -> results/btc/rr_grid.csv"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import btcfade as B, gold as G  # noqa: E402

GRID = dict(sl=[0.5, 0.75, 1.0, 1.5, 2.0, 3.0], rr=[0.17, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0], be=[0.0, 1.0],
            max_bars=[12, 48], trend_ema=[-50, 0], min_move=[2.5, 3.0])


def job(kw):
    m1 = B.data(ROOT)
    p = B.P(run_len=4, min_move=kw["min_move"], sl=kw["sl"], tp=kw["sl"] * kw["rr"], max_bars=kw["max_bars"],
            trend_ema=kw["trend_ema"], be=kw["be"], be_buf=0.1 if kw["be"] else 0.0)
    return {**kw, **G.stats(B.backtest(m1, p))}


if __name__ == "__main__":
    jobs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    with ProcessPoolExecutor(4) as ex:
        rows = list(ex.map(job, jobs, chunksize=8))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "btc" / "rr_grid.csv", index=False)
    print(len(df), "variants")
