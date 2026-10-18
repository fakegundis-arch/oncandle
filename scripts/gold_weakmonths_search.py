#!/usr/bin/env python3
"""Gold Asian breakout: search for settings that make April, July and September 2026 profitable.

Every engine setting x overlay x risk is stored with its month-by-month returns for Q4 2024, 2025 and 2026
(month of the trade's entry), so the weak-month targets can be checked against all other months.
    python scripts/gold_weakmonths_search.py  -> results/gold/weakmonths_search.parquet
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
from backtester.engine import njit  # noqa: E402

SESS = {"00-06": (0, 6), "01-06": (1, 6), "00-04": (0, 4), "00-08": (0, 8)}
ENGINE = dict(ses=list(SESS), don=[10, 15, 20], ema=[200, 400], slope=[8, 16], prev_day=[True, False],
              stop_atr=[1.5, 2.0, 2.5], rr=[3.0, 4.0], be_buf=[0.1, 0.3], regime_max=[99.0, 1.6, 1.3],
              max_per_day=[99, 2], stop_after_loss=[False, True])
EQ = [(0, 0.0), (5, -1.0), (10, -2.0), (10, -1.0), (15, -2.0), (20, -3.0)]
WEEK = [0.0, -2.0, -3.0]
RISK = [(0.12, 0.06), (0.10, 0.10)]
MONTHS = [f"{y}-{m:02d}" for y, m in [(2024, 10), (2024, 11), (2024, 12)]] + \
         [f"2025-{m:02d}" for m in range(1, 13)] + [f"2026-{m:02d}" for m in range(1, 11)]


@njit(cache=True)
def _overlay(r, week, eq_n, eq_thr, week_cap):
    n = len(r)
    take = np.ones(n, np.bool_)
    s = 0.0
    for i in range(n):
        if eq_n > 0 and i >= eq_n:
            if s < eq_thr:
                take[i] = False
        s += r[i]
        if eq_n > 0 and i >= eq_n:
            s -= r[i - eq_n]
    if week_cap < 0:
        cur = -1
        run = 0.0
        for i in range(n):
            if week[i] != cur:
                cur = week[i]
                run = 0.0
            if run <= week_cap:
                take[i] = False
            elif take[i]:
                run += r[i]
    return take


def job(ekw):
    m1, m15 = G.data(ROOT)
    s0, s1 = SESS[ekw["ses"]]
    t = G.backtest(m1, m15, G.P(**{k: v for k, v in ekw.items() if k != "ses"}, ses_start=s0, ses_end=s1))
    r = t.r.to_numpy(np.float64)
    iso = t.entry_time.dt.isocalendar()
    week = (iso.year * 100 + iso.week).to_numpy(np.int64)
    mk = t.entry_time.dt.strftime("%Y-%m").to_numpy()
    mi = pd.Index(MONTHS).get_indexer(mk)
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
    for c in [c for c in df if c.startswith("n20")]:
        df[c] = df[c].astype("int16")
    return df


def main():
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, jobs, chunksize=8)):
            parts.append(df)
            if i % 2000 == 0:
                print(i, "/", len(jobs), flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(ROOT / "results" / "gold" / "weakmonths_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
