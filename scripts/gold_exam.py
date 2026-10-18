"""Final exam: every built Gold Asian breakout version on gold data none of them was ever chosen or checked on
(Feb-Dec 2023 and Jan-Sep 2024; Jan 2023 is indicator warm-up), at the old $0.20 cost and at Dukascopy's recorded
spread. Uses data/XAUUSD_LONG_M1.csv (2023-01 -> 2026-10). Writes results/gold/exam.csv.
    python scripts/gold_exam.py [version ...]"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
import gold_versions as V  # noqa: E402

EXAM = {"2023": ("2023-02-01", "2024-01-01"), "2024": ("2024-01-01", "2024-10-01")}
COSTS = {"$0.20": dict(cost=0.20), "Dukascopy": dict(cost_mode="data")}


def run(versions, extra=None):
    gold = G.data(ROOT, "XAUUSD_LONG")
    rows, monthly = [], {}
    for v in versions:
        for cn, ck in COSTS.items():
            t = V.trades(extra[v] if extra and v in extra else v, *gold, **ck)
            r = {"version": v, "cost": cn}
            for k, (a, b) in EXAM.items():
                usd, dd, rets, n = V.book(t, a, b)
                r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": int((rets > 0).sum()), f"{k}_m": len(rets),
                          f"{k}_worst": float(rets.min()), f"{k}_n": n})
                monthly[(v, cn, k)] = rets
            rows.append(r)
    return pd.DataFrame(rows), monthly


if __name__ == "__main__":
    vs = sys.argv[1:] or list(V.VERSIONS)
    df, _ = run(vs)
    df.to_csv(ROOT / "results/gold/exam.csv", index=False)
    pd.set_option("display.width", 250)
    print(df.round(2).to_string())
