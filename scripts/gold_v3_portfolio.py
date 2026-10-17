#!/usr/bin/env python3
"""v3 portfolio: gold Asian breakout v3 + Truth Social tariff -> Dow + BTC H1 Run Fade + gold H4 MACD.
Each trade risks its stream's share x equity at entry; equity changes when trades close (overlaps allowed).
Weights chosen on 2025 (+ Q4 2024); 2026 is the check.   python scripts/gold_v3_portfolio.py"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import alt as A, data as D, indicators as ind  # noqa: E402
from backtester.engine import backtest  # noqa: E402
from backtester.strategies import macd_trend  # noqa: E402

PERIODS = {"q4_24": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}


def streams():
    g = pd.read_csv(ROOT / "results/gold/v3_trades.csv", parse_dates=["entry_time", "exit_time"])
    d = pd.read_csv(ROOT / "results/truth/tariff_us30_trades.csv", parse_dates=["entry_utc", "exit_utc"])
    d = d.rename(columns={"entry_utc": "entry_time", "exit_utc": "exit_time"})
    b = pd.read_csv(ROOT / "results/high_winrate/btc_h1_run_fade_m1_verified_trades.csv", parse_dates=["entry_time", "exit_time"])
    h4 = A.bars("XAUUSD", "4h")
    m = backtest(h4, macd_trend(h4, 12, 26, 9, 100), ind.atr(h4, 14), 1.5 * D.EXNESS_STANDARD_SPREAD["XAUUSD"],
                 stop_mult=3.0).trades
    return {"gold_v3": g, "dow_tariff": d, "btc_fade": b, "gold_h4_macd": m}


def book(S, w, a, b):
    ev = []
    for k, t in S.items():
        if w.get(k, 0) <= 0:
            continue
        x = t[(t.entry_time >= a) & (t.entry_time < b)]
        ev += [(e, 0, q, k, r) for q, (e, r) in enumerate(zip(x.entry_time, x.r))]
        ev += [(xt, 1, q, k, r) for q, (xt, r) in enumerate(zip(x.exit_time, x.r))]
    # entries before exits at the same minute, so a trade opened and stopped in one minute is still counted
    ev.sort(key=lambda z: (z[0], z[1]))
    eq, stake, curve = 1000.0, {}, [1000.0]
    for t, kind, q, k, r in ev:
        if kind == 0:
            stake[(k, q)] = w[k] * eq
        elif (k, q) in stake:
            eq = max(eq + stake.pop((k, q)) * r, 0.0)
            curve.append(eq)
    c = np.array(curve)
    return eq, (c / np.maximum.accumulate(c) - 1).min(), len(curve) - 1


def main():
    S = streams()
    for k, t in S.items():
        print(k, len(t), "trades")
    # correlation of monthly R sums
    mo = pd.DataFrame({k: t.groupby(t.entry_time.dt.to_period("M")).r.sum() for k, t in S.items()}).fillna(0)
    print(mo.corr().round(2))
    rows = []
    for wg, wd, wb, wm in itertools.product((0.03, 0.05, 0.07, 0.10), (0, 0.02, 0.04), (0, 0.02, 0.05), (0, 0.02, 0.04)):
        w = {"gold_v3": wg, "dow_tariff": wd, "btc_fade": wb, "gold_h4_macd": wm}
        row = dict(w)
        for p, (a, b) in PERIODS.items():
            e, dd, n = book(S, w, a, b)
            row.update({f"{p}_usd": e, f"{p}_dd": dd, f"{p}_n": n})
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results/gold/v3_portfolio_grid.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    df = main()
    df["mar25"] = (np.log(df.y25_usd / 1000) + np.log(df.q4_24_usd / 1000)) / -np.minimum(df.y25_dd, df.q4_24_dd)
    ok = df[np.minimum(df.y25_dd, df.q4_24_dd) >= -0.35]          # drawdown budget, set on 2025 + Q4 2024
    print(ok.sort_values("y25_usd", ascending=False).head(10).round(3).to_string(index=False))
    print(df.sort_values("mar25", ascending=False).head(10).round(3).to_string(index=False))
