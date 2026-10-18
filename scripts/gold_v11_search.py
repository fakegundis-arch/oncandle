#!/usr/bin/env python3
"""Gold Asian breakout v11 search: v10 plus more entries / bigger winners / overlay tuning, ONE rule set every month.

Every engine x overlay x risk is stored with month-by-month returns and the drawdown of each period.
Chosen on 2026 only (rule in scripts/gold_v11.py); 2025 and Q4 2024 are the test.
    python scripts/gold_v11_search.py  -> results/gold/v11_search.parquet
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_monthly_search import MONTHS, _overlay  # noqa: E402

ENGINE = dict(rr=[3.0, 4.0, 5.0, 6.0], trail_atr=[0.0, 2.0, 3.0], add=["none", "1R x0.5", "1R x1", "2R x1"],
              ses_end=[6, 8], don=[10, 15], d1_trend=[10, 20, 50], regime_max=[1.4, 1.6, 2.0],
              asian_range=[0, 60])
ADD = {"none": (0.0, 0.0), "1R x0.5": (1.0, 0.5), "1R x1": (1.0, 1.0), "2R x1": (2.0, 1.0)}
FIXED = dict(ema=400, slope=16, prev_day=True, stop_atr=1.5, be=1.0, be_buf=0.3, ses_start=0, regime_warmup=20)
EQ = [(0, 0.0), (5, -1.0), (10, -2.0), (10, -1.0), (15, -2.0), (20, -3.0)]
WEEK = [0.0, -2.0]
RISK = [(0.08, 0.08), (0.10, 0.10), (0.12, 0.12), (0.12, 0.08), (0.10, 0.06)]
PER = {"q4": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}


def params(ekw):
    kw = {**FIXED, **{k: v for k, v in ekw.items() if k != "add"}}
    kw["add_r"], kw["add_size"] = ADD[ekw["add"]]
    return G.P(**kw)


def job(ekw):
    m1, m15 = G.data(ROOT)
    t = G.backtest(m1, m15, params(ekw))
    r = t.r.to_numpy(np.float64)
    iso = t.entry_time.dt.isocalendar()
    week = (iso.year * 100 + iso.week).to_numpy(np.int64)
    mi = pd.Index(MONTHS).get_indexer(t.entry_time.dt.strftime("%Y-%m").to_numpy())
    pmask = {k: ((t.entry_time >= a) & (t.entry_time < b)).to_numpy() for k, (a, b) in PER.items()}
    d = t.dir.to_numpy()
    rows = []
    for (n, thr), wk in itertools.product(EQ, WEEK):
        tk = _overlay(r, week, n, thr, wk)
        for fl, fs in RISK:
            g = np.log(np.maximum(1 + np.where(d == 1, fl, fs) * r, 1e-9))
            ok = tk & (mi >= 0)
            lm = np.bincount(mi[ok], g[ok], len(MONTHS))
            row = {**ekw, "eq_n": n, "eq_thr": thr, "week_cap": wk, "risk": fl, "short": fs}
            row.update({f"m{k}": float(np.expm1(v)) for k, v in zip(MONTHS, lm)})
            for k, m in pmask.items():
                c = np.cumsum(g[tk & m])
                c = np.concatenate([[0.0], c])
                row[f"dd_{k}"] = float(np.expm1((c - np.maximum.accumulate(c)).min()))
                row[f"n_{k}"] = int((tk & m).sum())
            rows.append(row)
    df = pd.DataFrame(rows)
    for c in df.select_dtypes("float64"):
        df[c] = df[c].astype("float32")
    return df


def main():
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, jobs, chunksize=4)):
            parts.append(df)
            if i % 500 == 0:
                print(i, "/", len(jobs), flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(ROOT / "results" / "gold" / "v11_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
