#!/usr/bin/env python3
"""Gold Asian breakout v14: regime-proof search on 2023-2026 data with Dukascopy's recorded spread on every trade.

v11's two engines (Asia 00-06 Donchian 10, New York 12-15 Donchian 15, v10 filters) plus general protections:
minimum volatility (ATR % of price), a longer equity-curve pause, break-even and target; several risk splits.
Chosen on Feb-Dec 2023 (calm gold) AND 2026 (volatile gold); tested on Jan-Sep 2024 (never used for any choice),
Q4 2024 and 2025.  Rule (fixed before the test periods were looked at):
  1. 2026 profitable and Feb-Dec 2023 losing at most 10% (first fixed as "profitable in both": no setup managed it),
  2. drawdown >= -45% in both,
  3. at least half of the one-step neighbours also pass 1-2,  4. highest combined growth (product of both multiples).
    python scripts/gold_v14_regime.py            -> results/gold/v14_regime.parquet + selection view
    python scripts/gold_v14_regime.py --reveal   -> the pick on the test periods
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_versions import NY, V10, book  # noqa: E402
from gold_v3 import overlay  # noqa: E402

GRID = dict(atr_pct_min=[0.0, 0.06, 0.08, 0.10, 0.12], eq=["10/-2", "20/-2", "20/0", "30/-3", "30/0", "50/0"],
            be=[1.0, 1.5], be_buf=[0.3, 0.5], rr=[3.0, 4.0])
RISK = dict(w_asia=[0.04, 0.06, 0.08, 0.10], w_ny=[0.0, 0.02, 0.04])
SEL = {"s23": ("2023-02-01", "2024-01-01"), "s26": ("2026-01-01", "2026-11-01")}
TEST = {"t24": ("2024-01-01", "2024-10-01"), "q4": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01")}
OUT = ROOT / "results/gold/v14_regime.parquet"


def eq_overlay(s):
    n, thr = s.split("/")
    return int(n), float(thr), -2.0


def engines(kw, m1, m15):
    ch = dict(atr_pct_min=kw["atr_pct_min"], be=kw["be"], be_buf=kw["be_buf"], rr=kw["rr"], cost_mode="data")
    ov = eq_overlay(kw["eq"])
    return (overlay(G.backtest(m1, m15, replace(V10, **ch)), *ov), overlay(G.backtest(m1, m15, replace(NY, **ch)), *ov))


def job(kw):
    m1, m15 = G.data(ROOT, "XAUUSD_LONG")
    a, n = engines(kw, m1, m15)
    rows = []
    for wa, wn in itertools.product(*RISK.values()):
        t = pd.concat([a.assign(f=wa)] + ([n.assign(f=wn)] if wn > 0 else []))
        r = {**kw, "w_asia": wa, "w_ny": wn}
        for k, (s, e) in {**SEL, **TEST}.items():
            usd, dd, rets, cnt = book(t, s, e)
            r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": int((rets > 0).sum()), f"{k}_m": len(rets),
                      f"{k}_worst": float(rets.min()), f"{k}_n": cnt})
        rows.append(r)
    return rows


def search():
    jobs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    rows = []
    with ProcessPoolExecutor(4) as ex:
        for i, rs in enumerate(ex.map(job, jobs, chunksize=2)):
            rows += rs
            if i % 40 == 0:
                print(i, "/", len(jobs), flush=True)
    pd.DataFrame(rows).to_parquet(OUT, index=False)


def select(d):
    keys = list(GRID) + list(RISK)
    allv = {**GRID, **RISK}
    # rule 1 as first fixed ("profitable in both") had no candidates: no setup makes money in calm 2023 at real
    # spreads (best $989). Relaxed, still on the selection periods only, to "2023 loses at most 10%".
    d["pass"] = (d.s23_usd >= 900) & (d.s26_usd > 1000) & (d.s23_dd >= -0.45) & (d.s26_dd >= -0.45)
    d["growth"] = (d.s23_usd / 1000) * (d.s26_usd / 1000)
    look = d.set_index(keys)["pass"].to_dict()
    share = []
    for _, r in d.iterrows():
        if not r["pass"]:
            share.append(0.0); continue
        hits = tot = 0
        for k, opts in allv.items():
            p = opts.index(r[k])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    tot += 1; hits += bool(look.get(tuple(opts[q] if kk == k else r[kk] for kk in keys), False))
        share.append(hits / tot)
    d["nb"] = share
    return d[d["pass"] & (d.nb >= 0.5)].sort_values("growth", ascending=False)


def main(reveal=False):
    if not OUT.exists() or "--rerun" in sys.argv:
        search()
    d = pd.read_parquet(OUT)
    c = select(d)
    pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40)
    print(len(d), "setups |", int(d["pass"].sum()), "pass rules 1-2 |", len(c), "also rule 3")
    cols = list(GRID) + list(RISK) + ["s23_usd", "s23_dd", "s23_n", "s26_usd", "s26_dd", "s26_up", "nb"]
    print(c[cols].head(15).round(3).to_string())
    if reveal and len(c):
        p = c.iloc[0]
        print("\nPICK", {k: p[k] for k in list(GRID) + list(RISK)})
        for k in list(SEL) + list(TEST):
            print(f"  {k}: ${p[f'{k}_usd']:,.0f} DD {p[f'{k}_dd']:.0%} months up {p[f'{k}_up']}/{p[f'{k}_m']} "
                  f"worst {p[f'{k}_worst']:+.0%} trades {p[f'{k}_n']}")
    return d, c


if __name__ == "__main__":
    main("--reveal" in sys.argv)
