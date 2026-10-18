#!/usr/bin/env python3
"""Gold Asian breakout v6: v5-family engines + account rules that shape each month.
Account rules: weekly stop (R), monthly loss stop (% of the month's starting equity -> no new trades until next
month), monthly profit lock (after +X% in a month, risk x lock_mult), drawdown brake (risk x 0.5 while equity is more
than dd_cut below its peak), risk on longs and a short-side multiplier.
Chosen on 2026 (like v5); 2025 and Q4 2024 are the checks.  Each period starts at $1,000.
    python scripts/gold_v6_search.py   -> results/gold/v6_search.parquet"""
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
from backtester.engine import njit  # noqa: E402
from gold_v3 import overlay  # noqa: E402

ACCOUNT = dict(risk=[0.10, 0.12, 0.15, 0.20, 0.25], short_mult=[0.5, 1.0], week_cap=[0.0, -2.0, -3.0],
               m_stop=[0.0, -0.10, -0.15, -0.20, -0.30], m_lock=[0.0, 0.3, 0.6, 1.0], lock_mult=[0.5, 0.25, 0.0],
               dd_cut=[1.0, 0.3, 0.45])


@njit(cache=True)
def account(r, d, month, week, risk, short_mult, week_cap, m_stop, m_lock, lock_mult, dd_cut):
    eq = 1000.0
    peak = eq
    mdd = 0.0
    cur_m = -1
    m_start = eq
    m_halt = False
    cur_w = -1
    w_r = 0.0
    n_m = 0
    pos_m = 0
    worst = 0.0
    taken = 0
    for i in range(len(r)):
        if month[i] != cur_m:
            if cur_m >= 0:
                ret = eq / m_start - 1
                n_m += 1
                if ret > 0:
                    pos_m += 1
                worst = min(worst, ret)
            cur_m = month[i]
            m_start = eq
            m_halt = False
        if week[i] != cur_w:
            cur_w = week[i]
            w_r = 0.0
        if m_halt or (week_cap < 0 and w_r <= week_cap):
            continue
        f = risk if d[i] == 1 else risk * short_mult
        mret = eq / m_start - 1
        if m_lock > 0 and mret >= m_lock:
            f *= lock_mult
        if dd_cut < 1 and eq < peak * (1 - dd_cut):
            f *= 0.5
        if f <= 0:
            continue
        eq = max(eq * (1 + f * r[i]), 0.0)
        taken += 1
        w_r += r[i]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        if m_stop < 0 and eq / m_start - 1 <= m_stop:
            m_halt = True
    if cur_m >= 0:
        ret = eq / m_start - 1
        n_m += 1
        if ret > 0:
            pos_m += 1
        worst = min(worst, ret)
    return eq, mdd, pos_m, n_m, worst, taken


def trades(ekw):
    m1, m15 = G.data(ROOT)
    kw = {k: v for k, v in ekw.items() if k not in ("eq_n", "eq_thr")}
    t = G.backtest(m1, m15, G.P(**kw))
    if ekw["eq_n"]:
        t = overlay(t, int(ekw["eq_n"]), float(ekw["eq_thr"]), 0.0)
    return t


def job(ekw):
    t = trades(ekw)
    wk = t.entry_time.dt.isocalendar()
    week_id = (wk.year * 100 + wk.week).to_numpy(np.int64)
    month_id = (t.entry_time.dt.year * 100 + t.entry_time.dt.month).to_numpy(np.int64)
    r, d = t.r.to_numpy(np.float64), t.dir.to_numpy(np.int64)
    per = {k: ((t.entry_time >= a) & (t.entry_time < b)).to_numpy() for k, (a, b) in G.PERIODS.items()}
    rows = []
    for v in itertools.product(*ACCOUNT.values()):
        akw = dict(zip(ACCOUNT, v))
        if akw["m_lock"] == 0 and akw["lock_mult"] != 0.5:
            continue
        row = {**ekw, **akw}
        for k, m in per.items():
            e, dd, pm, nm, worst, n = account(r[m], d[m], month_id[m], week_id[m], *v)
            row.update({f"{k}_usd": e, f"{k}_dd": dd, f"{k}_pos_m": pm, f"{k}_n_m": nm, f"{k}_worst_m": worst, f"{k}_n": n})
        rows.append(row)
    df = pd.DataFrame(rows)
    for col in df.select_dtypes("float64"):
        df[col] = df[col].astype("float32")
    return df


def main():
    eng = pd.read_csv(ROOT / "results" / "gold" / "v6_engines.csv").to_dict("records")
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, eng, chunksize=2)):
            parts.append(df)
            if i % 25 == 0:
                print(i, "/", len(eng), flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(ROOT / "results" / "gold" / "v6_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
