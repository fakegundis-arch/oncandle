"""Gold Asian breakout v7: seasonal two-mode bot (mode B in Feb-Jul, v5 in Aug-Jan).

Mode B was chosen on Feb-Jul 2026 by scripts/gold_febjul_search.py and checked on Feb-Jul 2025.
Writes results/gold/v7_febjul_trades.csv (all-year mode-B trades after its overlays).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402

FEBJUL = {2, 3, 4, 5, 6, 7}


def run(x, a, b):
    y = x[(x.entry_time >= a) & (x.entry_time < b)]
    f = np.where(y.dir == 1, y.fl, y.fs)
    eq = 1000 * np.cumprod(1 + f * y.r.to_numpy())
    s = pd.Series(eq, index=y.exit_time.to_numpy())
    me = s.resample("ME").last().ffill()
    rets = me / me.shift().fillna(1000) - 1
    return eq[-1], (eq / np.maximum.accumulate(eq) - 1).min(), rets


def main():
    m1, m15 = G.data(ROOT)
    v5 = overlay(G.backtest(m1, m15, G.P(don=10, rr=4.0, stop_atr=1.5, be_buf=0.3, slope=16, max_per_day=2)), 0, 0.0, -2.0)
    b = overlay(G.backtest(m1, m15, G.P(ses_start=0, ses_end=6, don=10, ema=200, slope=8, stop_atr=1.5, rr=4.0, be_buf=0.3,
                                        regime_max=1.6)), 10, -2.0, -2.0)
    b.to_csv(ROOT / "results/gold/v7_febjul_trades.csv", index=False)
    v7 = pd.concat([v5[~v5.entry_time.dt.month.isin(FEBJUL)].assign(fl=0.12, fs=0.06),
                    b[b.entry_time.dt.month.isin(FEBJUL)].assign(fl=0.10, fs=0.10)]).sort_values("entry_time")
    for name, x in [("v5", v5.assign(fl=.12, fs=.06)), ("v7", v7)]:
        print("==", name)
        for k, (a, e) in G.PERIODS.items():
            usd, dd, rets = run(x, a, e)
            print(f"  {k}: ${usd:,.0f} DD {dd:.0%} months up {(rets > 0).sum()}/{len(rets)} | "
                  + " ".join(f"{m.strftime('%b')}:{r:+.0%}" for m, r in rets.items()))


if __name__ == "__main__":
    main()
