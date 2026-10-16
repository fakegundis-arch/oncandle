#!/usr/bin/env python3
"""Compare the NY-open straddle across markets with ONE scale-free grid.

Distances and stops are multiples of each market's own "opening unit" (the
median 15-minute opening range of the previous 20 opens), so a Dow point and
a EURUSD pip are treated alike.  Spread = Exness estimate, plus slippage of
1.5 x spread on every fill.  M1 model with the worst-case same-minute rule.

    python scripts/run_straddle_markets.py
"""
from __future__ import annotations

import itertools
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, straddle as st  # noqa: E402
from fetch_ny_open_ticks import trading_days  # noqa: E402
from run_straddle import summary  # noqa: E402

MARKETS = ["US30", "NAS100", "US500", "XAUUSD", "XAGUSD", "USOIL", "BTCUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCAD"]
GRID = dict(dist=(0.05, 0.1, 0.2, 0.3), sl=(0.15, 0.3, 0.6), rr=(1.0, 1.5, 2.0, 3.0), hold=(15, 30, 60))


def main():
    out = ROOT / "results" / "straddle"
    days = list(trading_days(date(2024, 10, 1), date(2026, 10, 15)))
    rows = []
    for mkt in MARKETS:
        f = ROOT / "data" / f"{mkt}_M1.csv"
        if not f.exists():
            print("no data for", mkt)
            continue
        m1 = D.load_csv(f).drop(columns="spread", errors="ignore")
        units = st.opening_units(m1, days)
        spread = D.EXNESS_STANDARD_SPREAD[mkt]
        for dist, sl, rr, hold in itertools.product(*GRID.values()):
            p = st.Params(dist=dist, sl=sl, rr=rr, expiry_s=300, max_hold_min=hold)
            t = st.backtest_m1(m1, days, p, spread, 1.5 * spread, units=units)
            row = {"market": mkt, "dist_u": dist, "sl_u": sl, "rr": rr, "hold": hold}
            for k, (a, b) in {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}.items():
                s = summary(t, a, b)
                row.update({f"{k}_{x}": s.get(x, np.nan) for x in ("n", "win", "pf", "usd", "dd")})
            rows.append(row)
        print("done", mkt, f"(median opening unit {np.median(list(units.values())):.5g})", flush=True)
    pd.DataFrame(rows).to_csv(out / "markets_grid.csv", index=False)


if __name__ == "__main__":
    main()
