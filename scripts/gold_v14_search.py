#!/usr/bin/env python3
"""Gold Asian breakout v14 search, with every trade charged Dukascopy's recorded spread at its entry minute.

Settings shared by both engines (Asia 00-06 Donchian 10, New York 12-15 Donchian 15, v10 filters), ONE rule set for
every month: stop, target, break-even, weekly-trend filter, pullback entry; booked for several risk splits.
Chosen on 2026 only (rule in scripts/gold_v14.py); 2025, Q4 2024 and 2023 - Sep 2024 are the tests.
    python scripts/gold_v14_search.py  -> results/gold/v14_search.parquet
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_versions import NY, OV10, V10, book  # noqa: E402
from gold_v3 import overlay  # noqa: E402

GRID = dict(stop_atr=[1.5, 2.0, 2.5], rr=[3.0, 4.0, 5.0], be=[1.0, 1.5], be_buf=[0.3, 0.5], w1_trend=[0, 10, 20],
            limit_atr=[0.0, 0.25])
RISK = dict(w_asia=[0.06, 0.08, 0.10, 0.12, 0.14], w_ny=[0.0, 0.02, 0.04])
COST = dict(cost_mode="data")
PER = {"y26": ("2026-01-01", "2026-11-01"), "y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}


def engines(kw, m1, m15):
    ch = dict(stop_atr=kw["stop_atr"], rr=kw["rr"], be=kw["be"], be_buf=kw["be_buf"], w1_trend=kw["w1_trend"],
              limit_atr=kw["limit_atr"], limit_bars=4, limit_keep_stop=True, **COST)
    return (overlay(G.backtest(m1, m15, replace(V10, **ch)), *OV10),
            overlay(G.backtest(m1, m15, replace(NY, **ch)), *OV10))


def job(kw):
    m1, m15 = G.data(ROOT)
    a, n = engines(kw, m1, m15)
    rows = []
    for wa, wn in itertools.product(*RISK.values()):
        t = pd.concat([a.assign(f=wa)] + ([n.assign(f=wn)] if wn > 0 else []))
        r = {**kw, "w_asia": wa, "w_ny": wn}
        for k, (s, e) in PER.items():
            usd, dd, rets, cnt = book(t, s, e)
            r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": int((rets > 0).sum()), f"{k}_worst": float(rets.min()),
                      f"{k}_n": cnt})
        rows.append(r)
    return rows


def main():
    jobs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, rs in enumerate(ex.map(job, jobs, chunksize=2)):
            rows += rs
            if i % 50 == 0:
                print(i, "/", len(jobs), flush=True)
    pd.DataFrame(rows).to_parquet(ROOT / "results/gold/v14_search.parquet", index=False)
    print(len(rows), "combinations")


if __name__ == "__main__":
    main()
