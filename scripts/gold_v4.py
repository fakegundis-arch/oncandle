#!/usr/bin/env python3
"""Gold Asian breakout v4: v2 signals (every trade kept), risk per trade tiered by trade quality.
Quality flags known at entry: long side, daily-trend agreement (D1 EMA20), normal volatility (ATR <= 2x median),
volatility regime (5-day / 60-day true range <= 1.4), equity-curve health (last 10 paper trades >= -2R),
week not already down 2R (paper). Risk = hi if the chosen flags all pass, else lo; also a points-based ladder.
Chosen on Q4 2024 + 2025 under a drawdown budget; 2026 is the check.
    python scripts/gold_v4.py   -> results/gold/v4_grid.csv, v4_flags.csv"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G, indicators as ind  # noqa: E402

V2 = dict(don=20, rr=4.0, slope=16, stop_atr=1.5, be_buf=0.3)
FLAGS = ["long", "d1", "vol", "regime", "eq", "week"]


def flags():
    m1, m15 = G.data(ROOT)
    t = G.backtest(m1, m15, G.P(**V2)).reset_index(drop=True)
    sig_t = t.entry_time.dt.floor("15min") - pd.Timedelta("15min")       # the M15 signal bar
    c = m15.close
    day = m15.index.normalize()
    dc = c.groupby(day).last()
    de = ind.ema(dc, 20).shift()
    dprev = dc.shift()
    d1_up = pd.Series(day.map(dprev > de), index=m15.index).fillna(False)
    d1_dn = pd.Series(day.map(dprev < de), index=m15.index).fillna(False)
    atr = ind.atr(m15, 14)
    vol = (atr / atr.rolling(100).median()) <= 2.0
    tr = ind.true_range(m15)
    reg = (tr.rolling(96 * 5).mean() / tr.rolling(96 * 60).mean()).shift() <= 1.4
    look = lambda s: s.reindex(sig_t, method="ffill").to_numpy()
    t["long"] = t.dir == 1
    t["d1"] = np.where(t.dir == 1, look(d1_up), look(d1_dn)).astype(bool)
    t["vol"] = look(vol).astype(bool)
    t["regime"] = np.nan_to_num(look(reg).astype(float), nan=1).astype(bool)
    r = t.r.to_numpy()
    cs = np.r_[0.0, np.cumsum(r)]
    t["eq"] = [i < 10 or cs[i] - cs[i - 10] >= -2.0 for i in range(len(r))]
    wk = t.entry_time.dt.isocalendar()
    key = (wk.year * 100 + wk.week).to_numpy()
    wflag, run, cur = [], 0.0, None
    for i in range(len(r)):
        if key[i] != cur:
            cur, run = key[i], 0.0
        wflag.append(run > -2.0)
        run += r[i]
    t["week"] = wflag
    return t


def grow(r, f):
    eq = 1000 * np.cumprod(np.maximum(1 + f * r, 0))
    return (eq[-1], (eq / np.maximum.accumulate(eq) - 1).min()) if len(eq) else (1000.0, 0.0)


def main():
    t = flags()
    t.to_csv(ROOT / "results" / "gold" / "v4_flags.csv", index=False)
    print(len(t), "v2 trades;", {f: round(t[f].mean(), 2) for f in FLAGS})
    for f in FLAGS:                                   # how good is each flag? (avg R when on / off, per period)
        line = f"{f:7s}"
        for k, (a, b) in G.PERIODS.items():
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            line += f" | {k} on {x[x[f]].r.mean():+.2f} ({x[f].sum()}) off {x[~x[f]].r.mean():+.2f} ({(~x[f]).sum()})"
        print(line)
    rows = []
    sets = [s for n in range(1, 5) for s in itertools.combinations(FLAGS, n)]
    for fs, hi, lo in itertools.product(sets, (0.08, 0.10, 0.12, 0.15, 0.20), (0.0, 0.02, 0.03, 0.05, 0.07)):
        if lo >= hi:
            continue
        good = t[list(fs)].all(axis=1).to_numpy()
        f = np.where(good, hi, lo)
        row = {"flags": "+".join(fs), "hi": hi, "lo": lo}
        for k, (a, b) in G.PERIODS.items():
            m = ((t.entry_time >= a) & (t.entry_time < b)).to_numpy()
            usd, dd = grow(t.r.to_numpy()[m], f[m])
            row.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_n_hi": int((good & m).sum())})
        rows.append(row)
    # ladder: risk = base + step x number of passed flags (all six)
    score = t[FLAGS].sum(axis=1).to_numpy()
    for base, step in itertools.product((0.0, 0.01, 0.02), (0.01, 0.015, 0.02, 0.025, 0.03)):
        f = base + step * score
        row = {"flags": "ladder", "hi": base, "lo": step}
        for k, (a, b) in G.PERIODS.items():
            m = ((t.entry_time >= a) & (t.entry_time < b)).to_numpy()
            usd, dd = grow(t.r.to_numpy()[m], f[m])
            row.update({f"{k}_usd": usd, f"{k}_dd": dd})
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "gold" / "v4_grid.csv", index=False)
    print(len(df), "sizing rules")


if __name__ == "__main__":
    main()
