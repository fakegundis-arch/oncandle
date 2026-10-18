#!/usr/bin/env python3
"""Gold Asian breakout v13 search: exit / entry mechanics shared by both v12 engines (Asia + New York), ONE rule set
for every month. Each combination is booked as a two-engine portfolio for several risk splits.
Chosen on 2026 only (rule in scripts/gold_v13.py); 2025 and Q4 2024 are the test.
    python scripts/gold_v13_search.py  -> results/gold/v13_search.parquet
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
from gold_v12 import book, stream  # noqa: E402
from gold_v11_check import ASIA, NY  # noqa: E402

GRID = dict(stop_atr=[1.25, 1.5, 2.0], rr=[3.0, 4.0, 5.0], be=[0.0, 0.75, 1.0, 1.5, 2.0], be_buf=[0.0, 0.3, 0.6],
            partial=["none", "half@1R", "half@2R"], strong_close=[0.0, 0.3, 0.5], exit_hour=[-1, 16, 20])
PARTIAL = {"none": (0.0, 1.5), "half@1R": (0.5, 1.0), "half@2R": (0.5, 2.0)}
RISK = [(0.10, 0.05), (0.12, 0.04), (0.12, 0.06), (0.14, 0.04)]


def job(kw):
    gold = G.data(ROOT)
    pf, pr = PARTIAL[kw["partial"]]
    ch = dict(stop_atr=kw["stop_atr"], rr=kw["rr"], be=kw["be"], be_buf=kw["be_buf"], partial=pf, partial_r=pr,
              strong_close=kw["strong_close"], exit_hour=kw["exit_hour"])
    a = stream(*gold, replace(ASIA, **ch))
    n = stream(*gold, replace(NY, **ch))
    rows = []
    for wa, wn in RISK:
        r = {**kw, "w_asia": wa, "w_ny": wn}
        for k, (usd, dd, up, nm, worst) in book(pd.concat([a.assign(f=wa), n.assign(f=wn)])).items():
            r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": up, f"{k}_worst": worst})
        r.update({"n26": int((a.entry_time.dt.year == 2026).sum() + (n.entry_time.dt.year == 2026).sum())})
        rows.append(r)
    return rows


def main():
    jobs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, rs in enumerate(ex.map(job, jobs, chunksize=4)):
            rows += rs
            if i % 250 == 0:
                print(i, "/", len(jobs), flush=True)
    pd.DataFrame(rows).to_parquet(ROOT / "results/gold/v13_search.parquet", index=False)
    print(len(rows), "combinations")


if __name__ == "__main__":
    main()
