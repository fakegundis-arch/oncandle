#!/usr/bin/env python3
"""The gold Asian breakout v3 method on Nasdaq, Dow and S&P 500, across sessions and many settings.
Signals on M15, trades simulated on M1 (backtester/gold.py), with and without the v3 overlays
(equity-curve filter 10 trades / -2R, weekly stop -2R). Chosen on Q4 2024 + 2025; 2026 is the check.
    python scripts/index_breakout.py      -> results/index_breakout/grid.parquet"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402

MARKETS = {"NAS100": 8.0, "US30": 10.0, "US500": 1.5}          # minimum stop in points (~0.25 x median M15 ATR)
SESSIONS = {"asian": (0, 6), "asian_late": (2, 7), "london_open": (7, 10), "london": (7, 12),
            "ny_open": (13, 16), "ny": (13, 20), "ny_afternoon": (16, 20), "all_day": (0, 24)}
GRID = dict(session=list(SESSIONS), don=[10, 20, 40], ema=[100, 400], slope=[4, 16], prev_day=[True, False],
            stop_atr=[1.0, 1.5, 2.0, 3.0], rr=[2.0, 3.0, 4.0], d1_trend=[0, 20], vol_max=[99.0, 2.0])
OVERLAYS = {"none": (0, 0.0, 0.0), "v3": (10, -2.0, -2.0)}


def job(args):
    m, kw = args
    m1, m15 = G.data(ROOT, m)
    s0, s1 = SESSIONS[kw["session"]]
    p = G.P(**{k: v for k, v in kw.items() if k != "session"}, ses_start=s0, ses_end=s1, be_buf=0.3,
            min_stop=MARKETS[m], cost=D.EXNESS_STANDARD_SPREAD[m])
    t = G.backtest(m1, m15, p)
    rows = []
    for name, (n, thr, wk) in OVERLAYS.items():
        x = overlay(t, n, thr, wk) if n else t
        rows.append({"market": m, **kw, "overlay": name, **G.stats(x)})
    return rows


def main():
    out = ROOT / "results" / "index_breakout"
    out.mkdir(parents=True, exist_ok=True)
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    rows = []
    for m in MARKETS:
        with ProcessPoolExecutor(4) as ex:
            for i, r in enumerate(ex.map(job, [(m, kw) for kw in combos], chunksize=16)):
                rows += r
                if i % 2000 == 0:
                    print(m, i, "/", len(combos), flush=True)
        pd.DataFrame(rows).to_parquet(out / "grid.parquet", index=False)      # save after each market
        print("done", m, flush=True)
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
