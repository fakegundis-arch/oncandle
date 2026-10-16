#!/usr/bin/env python3
"""Search session-based M1 strategies (Asian / London / New York) on BTC,
gold, Nasdaq and Dow.  Discovery 2025, validation 2026, Exness spreads.
For each variant: win rate / PF / return per year, and what $1,000 becomes in
2026 when risking the half-Kelly fraction estimated on 2025 (capped at 20%).

    python scripts/search_sessions.py --out results/sessions
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, hwr, sessions as S  # noqa: E402
from search_growth import grow, kelly  # noqa: E402


def yearly(t, a, b):
    r = t[(t.entry_time >= a) & (t.entry_time < b)].r.to_numpy()
    if not len(r):
        return r, {"n": 0}
    loss = -r[r < 0].sum()
    return r, {"n": len(r), "win": (r > 0).mean(), "avg_r": r.mean(),
               "pf": r[r > 0].sum() / loss if loss > 0 else np.inf}


def job(sym):
    df = D.load_csv(ROOT / "data" / f"{sym}_M1.csv").drop(columns="spread", errors="ignore")
    cost = D.EXNESS_STANDARD_SPREAD[sym]
    rows = []
    for fam, fn, p in S.families(sym):
        t = hwr.run(df, fn(df, **p), cost)
        r25, s25 = yearly(t, "2025-01-01", "2026-01-01")
        r26, s26 = yearly(t, "2026-01-01", "2027-01-01")
        row = {"market": sym, "family": fam, "params": str(p),
               **{f"2025_{k}": v for k, v in s25.items()}, **{f"2026_{k}": v for k, v in s26.items()}}
        if len(r25) >= 30:
            f, _ = kelly(r25)
            use = min(f / 2, 0.20)
            row["risk_from_2025"] = use
            row["usd_2026_kelly"], row["dd_2026_kelly"] = (v * (1000 if i == 0 else 1) for i, v in enumerate(grow(r26, use)))
            for fr in (0.02, 0.05, 0.10):
                m, dd = grow(r26, fr)
                row[f"usd_2026_{int(fr * 100)}pct"], row[f"dd_2026_{int(fr * 100)}pct"] = 1000 * m, dd
        rows.append(row)
    print("done", sym, len(rows), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "sessions"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for r in ex.map(job, ["XAUUSD", "NAS100", "US30", "BTCUSD"]):
            rows += r
    pd.DataFrame(rows).to_csv(out / "all_session_configs.csv", index=False)
    print(len(rows), "session variants tested")


if __name__ == "__main__":
    main()
