"""Gold Asian breakout v11, attempt 2: v10 plus a second v10-style engine on another session, both trading every month.
Chosen on 2026 only: >= 9/10 months up, drawdown >= -45%, 2026 total above v10 at 8%, then the highest 2026 total.
Writes results/gold/v11_sessions.csv."""
import itertools
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

V10W = replace(V10, regime_warmup=20)
SESSIONS = [(6, 9), (7, 10), (8, 11), (12, 15), (13, 16)]
DON = [10, 15, 20]
SPLIT = [(0.08, 0.0), (0.06, 0.04), (0.06, 0.06), (0.08, 0.04), (0.08, 0.06), (0.08, 0.08), (0.10, 0.05)]


def main():
    m1, m15 = G.data(ROOT)
    base = overlay(G.backtest(m1, m15, V10W), *V10_OVERLAY).assign(engine="asia")
    rows = []
    for (s0, s1), don in itertools.product(SESSIONS, DON):
        p = replace(V10W, ses_start=s0, ses_end=s1, don=don)
        t2 = overlay(G.backtest(m1, m15, p), *V10_OVERLAY).assign(engine="second")
        for wa, wb in SPLIT:
            t = pd.concat([base.assign(f=wa), t2.assign(f=wb)]) if wb > 0 else base.assign(f=wa)
            row = {"ses": f"{s0:02d}-{s1:02d}", "don": don, "w_asia": wa, "w_second": wb}
            for k, (a, b) in G.PERIODS.items():
                e, dd, rets, n = sim(t.sort_values("entry_time"), a, b)
                row.update({f"{k}_usd": e, f"{k}_dd": dd, f"{k}_up": int((rets > 0).sum()), f"{k}_worst": float(rets.min()),
                            f"{k}_n": n})
            rows.append(row)
        print(s0, s1, don, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results/gold/v11_sessions.csv", index=False)


if __name__ == "__main__":
    main()
