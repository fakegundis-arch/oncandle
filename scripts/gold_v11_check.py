"""Gold Asian breakout v11: v10 (Asian session, 10%) + a v10-style New York engine (12:00-15:00, Donchian 15, 5%),
both trading every month. Writes results/gold/v11_trades.csv."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_v9 import sim  # noqa: E402
from gold_v10_check import V10, V10_OVERLAY  # noqa: E402

ASIA = replace(V10, regime_warmup=20)
NY = replace(ASIA, ses_start=12, ses_end=15, don=15)
W_ASIA, W_NY = 0.10, 0.05


def main():
    m1, m15 = G.data(ROOT)
    a = overlay(G.backtest(m1, m15, ASIA), *V10_OVERLAY).assign(engine="asia", f=W_ASIA)
    n = overlay(G.backtest(m1, m15, NY), *V10_OVERLAY).assign(engine="ny", f=W_NY)
    t = pd.concat([a, n]).sort_values("entry_time")
    t.to_csv(ROOT / "results/gold/v11_trades.csv", index=False)
    for k, (s, e) in G.PERIODS.items():
        usd, dd, rets, cnt_all = sim(t, s, e)
        y = t[(t.entry_time >= s) & (t.entry_time < e)]
        cnt = y.groupby(y.entry_time.dt.to_period("M")).size()
        print(f"{k}: ${usd:,.0f} DD {dd:.0%} trades {cnt_all} (asia {(y.engine == 'asia').sum()}, ny {(y.engine == 'ny').sum()}) "
              f"win {(y.r > 0).mean():.0%} months up {(rets > 0).sum()}/{len(rets)}")
        print("   " + " | ".join(f"{m.strftime('%b')} {r:+.0%} ({cnt.get(pd.Period(m, 'M'), 0)})" for m, r in rets.items()))
        for eng in ("asia", "ny"):
            z = y[y.engine == eng]
            print(f"     {eng}: {len(z)} trades, win {(z.r > 0).mean():.0%}, avg {z.r.mean():+.2f}R")


if __name__ == "__main__":
    main()
