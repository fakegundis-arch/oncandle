"""Gold Asian breakout v8: v7 (mode B Feb-Jul, v5 Aug-Jan) with mode C in April, July and September.

Mode C was chosen by scripts/gold_weakmonths_search.py: April, July and September 2026 all > +10%, ranked by the same
three months of 2025. Writes results/gold/v8_trades.csv (the combined real trades).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_v7 import run  # noqa: E402

MODE_B = {2, 3, 5, 6}
MODE_C = {4, 7, 9}


def streams(m1, m15):
    v5 = overlay(G.backtest(m1, m15, G.P(don=10, rr=4.0, stop_atr=1.5, be_buf=0.3, slope=16, max_per_day=2)), 0, 0.0, -2.0)
    b = overlay(G.backtest(m1, m15, G.P(ses_start=0, ses_end=6, don=10, ema=200, slope=8, stop_atr=1.5, rr=4.0, be_buf=0.3,
                                        regime_max=1.6)), 10, -2.0, -2.0)
    c = overlay(G.backtest(m1, m15, G.P(ses_start=0, ses_end=8, don=15, ema=200, slope=8, prev_day=False, stop_atr=1.5,
                                        rr=4.0, be_buf=0.3, max_per_day=2)), 10, -2.0, -2.0)
    return v5, b, c


def combine(v5, b, c, b_months=MODE_B, c_months=MODE_C):
    m = lambda t: t.entry_time.dt.month
    return pd.concat([v5[~m(v5).isin(b_months | c_months)].assign(fl=0.12, fs=0.06, mode="v5"),
                      b[m(b).isin(b_months)].assign(fl=0.10, fs=0.10, mode="B"),
                      c[m(c).isin(c_months)].assign(fl=0.10, fs=0.10, mode="C")]).sort_values("entry_time")


def main():
    m1, m15 = G.data(ROOT)
    v5, b, c = streams(m1, m15)
    v7 = combine(v5, b, c, {2, 3, 4, 5, 6, 7}, set())
    v8 = combine(v5, b, c)
    v8.to_csv(ROOT / "results/gold/v8_trades.csv", index=False)
    for name, x in [("v5", v5.assign(fl=.12, fs=.06)), ("v7", v7), ("v8", v8), ("C all year", c.assign(fl=.10, fs=.10))]:
        print("==", name)
        for k, (a, e) in G.PERIODS.items():
            usd, dd, rets = run(x, a, e)
            n = ((x.entry_time >= a) & (x.entry_time < e)).sum()
            print(f"  {k}: ${usd:,.0f} DD {dd:.0%} trades {n} months up {(rets > 0).sum()}/{len(rets)} | "
                  + " ".join(f"{m.strftime('%b')}:{r:+.0%}" for m, r in rets.items()))


if __name__ == "__main__":
    main()
