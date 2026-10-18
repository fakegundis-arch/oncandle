"""Gold Asian breakout v10: trade-level results for the pick from scripts/gold_v10.py (and v5 for comparison).
Writes results/gold/v10_trades.csv."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_v9 import sim  # noqa: E402

V10 = G.P(don=10, ema=400, slope=16, prev_day=True, stop_atr=1.5, rr=4.0, be=1.0, be_buf=0.3, d1_trend=20,
          regime_max=1.6)
V10_OVERLAY = (10, -2.0, -2.0)
V10_RISK = (0.08, 0.08)
V5 = G.P(don=10, rr=4.0, stop_atr=1.5, be_buf=0.3, slope=16, max_per_day=2)


def report(name, t, fl, fs):
    t = t.assign(f=np.where(t.dir == 1, fl, fs))
    print("==", name)
    for k, (a, b) in G.PERIODS.items():
        e, dd, rets, n = sim(t, a, b)
        y = t[(t.entry_time >= a) & (t.entry_time < b)]
        cnt = y.groupby(y.entry_time.dt.to_period("M")).size()
        print(f"  {k}: ${e:,.0f} DD {dd:.0%} trades {n} win {(y.r > 0).mean():.0%} months up {(rets > 0).sum()}/{len(rets)}")
        print("    " + " | ".join(f"{m.strftime('%b')} {r:+.0%} ({cnt.get(pd.Period(m, 'M'), 0)})" for m, r in rets.items()))
    return t


def main():
    m1, m15 = G.data(ROOT)
    report("v5", overlay(G.backtest(m1, m15, V5), 0, 0.0, -2.0), 0.12, 0.06)
    t = overlay(G.backtest(m1, m15, V10), *V10_OVERLAY)
    report("v10 (regime filter needs 60 days)", t, *V10_RISK)
    from dataclasses import replace
    t20 = overlay(G.backtest(m1, m15, replace(V10, regime_warmup=20)), *V10_OVERLAY)
    report("v10 (regime filter starts after 20 days: Q4 2024 measurable)", t20, *V10_RISK)
    t20.to_csv(ROOT / "results/gold/v10_trades.csv", index=False)
    for fl in (0.10, 0.12):
        report(f"v10 at {fl:.0%} risk", t20, fl, fl)


if __name__ == "__main__":
    main()
