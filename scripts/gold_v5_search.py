#!/usr/bin/env python3
"""Gold Asian breakout v5: settings CHOSEN ON 2026; 2025 and Q4 2024 are the out-of-sample check.
Wider engine grid around the v2-v4 family x overlays x risk 10-25% x short size.
    python scripts/gold_v5_search.py   -> results/gold/v5_search.parquet"""
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

ENGINE = dict(don=[10, 12, 15, 18, 20], rr=[3.0, 4.0, 5.0], stop_atr=[1.25, 1.5, 2.0], be_buf=[0.1, 0.3, 0.5],
              slope=[8, 16], d1_trend=[0, 20], vol_max=[99.0, 2.0], regime_max=[99.0, 1.6],
              stop_after_loss=[False, True], max_per_day=[99, 2])
OVER = [(0, 0.0, 0.0), (0, 0.0, -2.0), (0, 0.0, -3.0), (10, -2.0, 0.0), (10, -2.0, -2.0), (10, -4.0, -3.0),
        (20, -4.0, 0.0), (20, -4.0, -3.0)]
RISK = [0.10, 0.12, 0.15, 0.20, 0.25]
SHORT_MULT = [1.0, 0.5]


def grow(r, f):
    eq = 1000 * np.cumprod(np.maximum(1 + f * r, 0))
    return (eq[-1], (eq / np.maximum.accumulate(eq) - 1).min()) if len(eq) else (1000.0, 0.0)


def job(ekw):
    m1, m15 = G.data(ROOT)
    t = G.backtest(m1, m15, G.P(**ekw))
    rows = []
    for n, thr, wk in OVER:
        x = overlay(t, n, thr, wk) if (n or wk) else t
        r, d = x.r.to_numpy(), x.dir.to_numpy()
        per = {k: ((x.entry_time >= a) & (x.entry_time < b)).to_numpy() for k, (a, b) in G.PERIODS.items()}
        for risk, sm in itertools.product(RISK, SHORT_MULT):
            f = np.where(d == 1, risk, risk * sm)
            row = {**ekw, "eq_n": n, "eq_thr": thr, "week_cap": wk, "risk": risk, "short_mult": sm}
            for k, m in per.items():
                usd, dd = grow(r[m], f[m])
                pf_r = r[m]
                row.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_n": int(m.sum()),
                            f"{k}_pf": pf_r[pf_r > 0].sum() / max(-pf_r[pf_r < 0].sum(), 1e-9)})
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    jobs = [dict(zip(ENGINE, v)) for v in itertools.product(*ENGINE.values())]
    parts = []
    with ProcessPoolExecutor(4) as ex:
        for i, df in enumerate(ex.map(job, jobs, chunksize=8)):
            parts.append(df)
            if i % 500 == 0:
                print(i, "/", len(jobs), flush=True)
    out = pd.concat(parts, ignore_index=True)
    for col in out.select_dtypes("float64"):
        out[col] = out[col].astype("float32")
    out.to_parquet(ROOT / "results" / "gold" / "v5_search.parquet", index=False)
    print(len(out), "combinations")


if __name__ == "__main__":
    main()
