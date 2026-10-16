#!/usr/bin/env python3
"""Search for strategies with a >70% win rate that are ALSO profitable after
costs, without fooling ourselves:
    discovery  = 2025 (pick candidates here)
    validation = 2026 (never used for picking; must still hold)

    python scripts/search_high_winrate.py --out results/high_winrate
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtester import data as D  # noqa: E402
from backtester import hwr  # noqa: E402

MARKETS = ["XAUUSD", "NAS100", "US30", "BTCUSD"]
TFS = ["5min", "15min", "1h"]
PERIODS = {"2025": ("2025-01-01", "2026-01-01"), "2026": ("2026-01-01", "2027-01-01")}
RISK = 0.005


def load(sym, tf):
    df = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df.resample(tf).agg(agg).dropna()


def stats(t: pd.DataFrame) -> dict:
    if len(t) == 0:
        return {"n": 0}
    r = t.r.to_numpy()
    eq = np.cumprod(1 + RISK * r)
    loss = -r[r < 0].sum()
    return {"n": len(r), "win": (r > 0).mean(), "avg_r": r.mean(),
            "pf": r[r > 0].sum() / loss if loss > 0 else np.inf,
            "ret": eq[-1] - 1, "dd": (eq / np.maximum.accumulate(eq) - 1).min(),
            "avg_win": r[r > 0].mean() if (r > 0).any() else 0, "avg_loss": r[r < 0].mean() if (r < 0).any() else 0}


def job(args):
    sym, tf = args
    df = load(sym, tf)
    cost = D.EXNESS_STANDARD_SPREAD[sym]
    rows = []
    for fam, (fn, grid) in hwr.FAMILIES.items():
        for p in grid:
            t = hwr.run(df, fn(df, **p), cost)
            row = {"market": sym, "tf": tf, "family": fam, "params": str(p)}
            for k, (a, b) in PERIODS.items():
                s = stats(t[(t.entry_time >= a) & (t.entry_time < b)])
                row.update({f"{k}_{m}": v for m, v in s.items()})
            rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "high_winrate"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(m, tf) for m in MARKETS for tf in TFS]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for r in ex.map(job, jobs):
            rows += r
            print(f"done {r[0]['market']} {r[0]['tf']}: {len(r)} configs", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "all_configs.csv", index=False)
    print(f"{len(df)} configurations tested")


if __name__ == "__main__":
    main()
