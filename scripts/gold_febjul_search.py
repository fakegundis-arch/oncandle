#!/usr/bin/env python3
"""Gold Asian breakout: settings for February-July. Chosen on Feb-Jul 2026, checked on Feb-Jul 2025 (and the full
years with a seasonal two-mode bot).   python scripts/gold_febjul_search.py  -> results/gold/febjul_search.parquet"""
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
from gold_v3 import overlay  # noqa: E402

SESS = {"00-06": (0, 6), "00-04": (0, 4), "01-06": (1, 6), "00-08": (0, 8), "23-06": (23, 6)}
ENGINE = dict(ses=list(SESS), don=[10, 15, 20, 30], ema=[200, 400], slope=[8, 16], prev_day=[True, False],
              stop_atr=[1.5, 2.0, 2.5, 3.0], rr=[2.0, 3.0, 4.0], be_buf=[0.1, 0.3], d1_trend=[0, 20], vol_max=[99.0, 2.0],
              regime_max=[99.0, 1.4, 1.6], max_per_day=[99, 2])
OVER = [(0, 0.0, 0.0), (0, 0.0, -2.0), (10, -2.0, 0.0), (10, -2.0, -2.0)]
WINDOWS = {"fj26": ("2026-02-01", "2026-08-01"), "fj25": ("2025-02-01", "2025-08-01")}
RISK = [(0.12, 0.06), (0.10, 0.10)]


def stats(x, fl, fs):
    if len(x) == 0:
        return 1000.0, 0.0, 0, 0, 0.0
    f = np.where(x.dir.to_numpy() == 1, fl, fs)
    eq = 1000 * np.cumprod(np.maximum(1 + f * x.r.to_numpy(), 0))
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    s = pd.Series(eq, index=x.exit_time.to_numpy())
    me = s.resample("ME").last().ffill()
    starts = me.shift().fillna(1000.0)
    rets = me / starts - 1
    return eq[-1], dd, int((rets > 0).sum()), len(rets), float(rets.min())


def job(ekw):
    m1, m15 = G.data(ROOT)
    s0, s1 = SESS[ekw["ses"]]
    t = G.backtest(m1, m15, G.P(**{k: v for k, v in ekw.items() if k != "ses"}, ses_start=s0, ses_end=s1))
    rows = []
    for n, thr, wk in OVER:
        x = overlay(t, n, thr, wk) if (n or wk) else t
        for fl, fs in RISK:
            row = {**ekw, "eq_n": n, "week_cap": wk, "risk": fl, "short": fs}
            for k, (a, b) in WINDOWS.items():
                y = x[(x.entry_time >= a) & (x.entry_time < b)]
                e, dd, pm, nm, worst = stats(y, fl, fs)
                row.update({f"{k}_usd": e, f"{k}_dd": dd, f"{k}_pos_m": pm, f"{k}_worst_m": worst, f"{k}_n": len(y)})
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
            if i % 2000 == 0:
                print(i, "/", len(jobs), flush=True)
    out = pd.concat(parts, ignore_index=True)
    out.to_parquet(ROOT / "results" / "gold" / "febjul_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
