#!/usr/bin/env python3
"""Gold Asian breakout v10 search: v5 plus general filters / exits, ONE rule set for every month.

Every engine x overlay x risk is run all year and stored with month-by-month returns (Q4 2024, 2025, 2026).
Chosen on 2026 only (rule in scripts/gold_v10.py); 2025 and Q4 2024 are the test.
    python scripts/gold_v10_search.py  -> results/gold/v10_search.parquet
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

ENGINE = dict(don=[10, 15], slope=[8, 16], stop_atr=[1.5, 2.0], rr=[3.0, 4.0], be=[1.0, 1.5], max_per_day=[2, 99],
              stop_after_loss=[False, True], pd_range_min=[0.0, 0.5, 0.7, 0.9], d1_trend=[0, 20],
              skip_mon=[False, True], regime_max=[99.0, 1.6], partial=[0.0, 0.5])
FIXED = dict(ema=400, prev_day=True, be_buf=0.3, ses_start=0, ses_end=6, partial_r=2.0)
EQ = [(0, 0.0), (10, -2.0), (5, -1.0)]
WEEK = [0.0, -2.0]
RISK = [(0.12, 0.06), (0.10, 0.10), (0.10, 0.05), (0.08, 0.08)]


def params(ekw):
    kw = {**FIXED, **{k: v for k, v in ekw.items() if k != "skip_mon"}}
    kw["skip_weekdays"] = (0,) if ekw["skip_mon"] else ()
    return G.P(**kw)


def job(ekw):
    m1, m15 = G.data(ROOT)
    t = G.backtest(m1, m15, params(ekw))
    r = t.r.to_numpy(np.float64)
    iso = t.entry_time.dt.isocalendar()
    week = (iso.year * 100 + iso.week).to_numpy(np.int64)
    mi = pd.Index(MONTHS).get_indexer(t.entry_time.dt.strftime("%Y-%m").to_numpy())
    d = t.dir.to_numpy()
    rows = []
    for (n, thr), wk in itertools.product(EQ, WEEK):
        tk = _overlay(r, week, n, thr, wk)
        for fl, fs in RISK:
            g = np.log(np.maximum(1 + np.where(d == 1, fl, fs) * r, 1e-9))
            ok = tk & (mi >= 0)
            lm = np.bincount(mi[ok], g[ok], len(MONTHS))
            cnt = np.bincount(mi[ok], minlength=len(MONTHS))
            row = {**ekw, "eq_n": n, "eq_thr": thr, "week_cap": wk, "risk": fl, "short": fs}
            row.update({f"m{k}": float(np.expm1(v)) for k, v in zip(MONTHS, lm)})
            row.update({f"n{k}": int(c) for k, c in zip(MONTHS, cnt)})
            rows.append(row)
    df = pd.DataFrame(rows)
    for c in df.select_dtypes("float64"):
        df[c] = df[c].astype("float32")
    return df


def main():
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, jobs, chunksize=8)):
            parts.append(df)
            if i % 1000 == 0:
                print(i, "/", len(jobs), flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(ROOT / "results" / "gold" / "v10_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
