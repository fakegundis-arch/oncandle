#!/usr/bin/env python3
"""NY-open straddle backtest on Nasdaq and Dow, 10% risk per trade, $1,000 start.

    python scripts/run_straddle.py                 # M1, every open Oct 2024 - Oct 2026
    python scripts/run_straddle.py --ticks         # tick-level, on the days with cached ticks
"""
from __future__ import annotations

import argparse
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

RISK = 0.10
GRID = {
    "NAS100": dict(dist=(5, 10, 20, 30), sl=(10, 20, 40), slip=(0, 2, 5)),
    "US30": dict(dist=(10, 20, 40, 60), sl=(20, 40, 80), slip=(0, 4, 10)),
}
DEFAULT = {"NAS100": dict(dist=10, sl=20, slip=2), "US30": dict(dist=20, sl=40, slip=4)}


def grow(r):
    if len(r) == 0:
        return 1.0, 0.0
    eq = np.cumprod(np.maximum(1 + RISK * r, 0))
    return eq[-1], (eq / np.maximum.accumulate(eq) - 1).min()


def summary(t, a, b):
    x = t[(t.date >= a) & (t.date < b)] if len(t) else t
    r = x.r.to_numpy() if len(x) else np.array([])
    if not len(r):
        return {"n": 0}
    m, dd = grow(r)
    loss = -r[r < 0].sum()
    return {"n": len(r), "win": (r > 0).mean(), "avg_r": r.mean(),
            "pf": r[r > 0].sum() / loss if loss > 0 else np.inf, "usd": 1000 * m, "dd": dd}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "results" / "straddle"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    days = list(trading_days(date(2024, 10, 1), date(2026, 10, 15)))
    periods = {"2025": ("2025-01-01", "2026-01-01"), "2026": ("2026-01-01", "2027-01-01")}
    rows = []
    for mkt in ("NAS100", "US30"):
        spread = D.EXNESS_STANDARD_SPREAD[mkt]
        m1 = None if a.ticks else D.load_csv(ROOT / "data" / f"{mkt}_M1.csv").drop(columns="spread", errors="ignore")
        g = GRID[mkt]
        for dist, sl, rr, exp, hold, slip in itertools.product(g["dist"], g["sl"], (1.0, 2.0, 3.0), (60, 300),
                                                                (15, 30, 60), g["slip"]):
            if a.ticks and (slip != g["slip"][0] or hold > 29):
                continue                      # ticks already contain real slippage; 1 cached hour
            p = st.Params(dist=dist, sl=sl, rr=rr, expiry_s=exp, max_hold_min=hold)
            t = st.backtest(mkt, days, p) if a.ticks else st.backtest_m1(m1, days, p, spread, slip)
            row = {"market": mkt, "dist": dist, "sl": sl, "rr": rr, "expiry_s": exp, "hold_min": hold, "slip": slip}
            for k, (x0, x1) in periods.items():
                row.update({f"{k}_{m}": v for m, v in summary(t, x0, x1).items()})
            rows.append(row)
        print("done", mkt, flush=True)
    res = pd.DataFrame(rows)
    res.to_csv(out / ("grid_ticks.csv" if a.ticks else "grid_m1.csv"), index=False)
    print(len(res), "configurations")


if __name__ == "__main__":
    main()
