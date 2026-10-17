#!/usr/bin/env python3
"""Fill the gaps: range-pair mean reversion (+ news filter), session-TWAP reversion, cointegration-gated pairs,
trend following on GBPJPY / USDJPY (H1-D1), London-open range breakout.  Chosen on 2025 (+ Q4 2024), judged on 2026.

    python scripts/fetch_dukascopy_m1.py EURCHF AUDNZD EURGBP AUDUSD NZDUSD GBPJPY --bid-only
    python scripts/run_gaps.py [mr pairs trend orb]          # -> results/gaps/*.csv
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import alt as A, data as D, gaps as G, hwr, indicators as ind, sessions as SS  # noqa: E402
from backtester.engine import backtest  # noqa: E402
from backtester.strategies import STRATEGIES  # noqa: E402

OUT = ROOT / "results" / "gaps"
MR_MARKETS = ["EURCHF", "AUDNZD", "EURGBP", "AUDUSD", "NZDUSD", "EURUSD", "GBPUSD"]
_CAL = {}


def cal():
    if not _CAL:
        c = pd.read_csv(ROOT / "data" / "calendar" / "ff_calendar.csv", parse_dates=["time_utc"])
        _CAL["c"] = c
    return _CAL["c"]


def grid(d):
    return [dict(zip(d, v)) for v in itertools.product(*d.values())]


# ---------------------------------------------------------------- 1. mean reversion
MR_GRID = {
    "bb": dict(n=(20, 50), k=(2.0, 2.5, 3.0), target=("mid", "band")),
    "rsi": dict(n=(2, 3), lo=(5.0, 10.0, 20.0), tp_atr=(0.5, 1.0, 2.0)),
    "twap": dict(z=(1.5, 2.0, 2.5, 3.0)),
}
MR_COMMON = dict(sl_atr=(1.5, 3.0, 5.0), ses=("asian", "all", "london"), news=(True, False), max_bars=(12, 48))


def mr_job(args):
    m, tf, fam = args
    df = A.bars(m, tf)
    nm = G.news_mask(df.index, cal(), G.CCY[m])
    cost = 1.5 * D.EXNESS_STANDARD_SPREAD[m]
    fn = {"bb": G.bb_fade, "rsi": G.rsi_fade, "twap": G.twap_fade}[fam]
    rows = []
    for p in grid(MR_GRID[fam]):
        for q in grid(MR_COMMON):
            kw = {**p, **q, "news": nm if q["news"] else None}
            t = hwr.run(df, fn(df, **kw), cost)
            rows.append({"market": m, "tf": tf, "family": fam, **p, **q, **A.stats(t)})
    return rows


# ---------------------------------------------------------------- 2. pairs with a cointegration gate
PAIRS = [("AUDUSD", "NZDUSD"), ("EURUSD", "GBPUSD"), ("EURCHF", "EURUSD"), ("EURGBP", "EURUSD")]
BPD = {"15min": 96, "1h": 24}


def pairs_job(args):
    (a, b), tf, L_days, crit = args
    bpd = BPD[tf]
    A_, B_ = A.bars(a, tf).close, A.bars(b, tf).close
    j = pd.concat([A_.rename("a"), B_.rename("b")], axis=1, join="inner").dropna()
    la, lb = np.log(j.a), np.log(j.b)
    L = int(L_days * bpd)
    ma, mb = la.rolling(L).mean().shift(), lb.rolling(L).mean().shift()
    va, vb = la.rolling(L).var().shift(), lb.rolling(L).var().shift()
    cov = la.rolling(L).cov(lb).shift()
    beta = cov / vb
    s, mu, sd = la - beta * lb, ma - beta * mb, np.sqrt((va - beta * cov).clip(lower=0))
    gate = np.ones(len(j), bool) if crit is None else G.coint_gate(la, lb, L, bpd, crit)
    cost = 1.5 * (D.EXNESS_STANDARD_SPREAD[a] / j.a.median() + abs(beta.median()) * D.EXNESS_STANDARD_SPREAD[b] / j.b.median())
    rows = []
    for zin, zgap, hold in itertools.product((1.5, 2.0, 2.5), (1.5, 3.0), (1, 5)):
        ent, ex, R = G.gated_pairs(la.to_numpy(), lb.to_numpy(), beta.to_numpy(), s.to_numpy(), mu.to_numpy(),
                                   sd.to_numpy(), gate, zin, zin + zgap, int(hold * bpd), cost)
        ok = ent >= 0
        t = pd.DataFrame({"entry_time": j.index[ent[ok]], "exit_time": j.index[ex[ok]], "r": R[ok]})
        rows.append({"pair": f"{a}/{b}", "tf": tf, "L_days": L_days, "crit": crit if crit is not None else 0.0,
                     "zin": zin, "zgap": zgap, "hold_days": hold, "gate_share": gate.mean(), **A.stats(t)})
    return rows


# ---------------------------------------------------------------- 3. trend following
def trend_job(args):
    m, tf = args
    df = A.bars(m, tf)
    atr = ind.atr(df, 14)
    cost = 1.5 * D.EXNESS_STANDARD_SPREAD[m]
    rows = []
    for name, (fn, params, risks) in STRATEGIES.items():
        for p in params:
            sig = fn(df, **p)
            for r in risks:
                t = backtest(df, sig, atr, cost, **r).trades
                rows.append({"market": m, "tf": tf, "strategy": name, "params": str(p), **r, **A.stats(t)})
    return rows


# ---------------------------------------------------------------- 4. London-open range breakout
def orb_job(m):
    df = A.bars(m, "5min")
    cost = 1.5 * D.EXNESS_STANDARD_SPREAD[m]
    rows = []
    for rng, slm, tp, be, eh in itertools.product((15, 30, 60), ("range", "mid"), (1.0, 2.0, 3.0), (0.0, 1.0), (2.0, 4.0)):
        t = hwr.run(df, SS.orb(df, "london", range_min=rng, sl_mode=slm, tp_mult=tp, be=be, entry_hours=eh), cost)
        rows.append({"market": m, "range_min": rng, "sl": slm, "tp": tp, "be": be, "entry_hours": eh, **A.stats(t)})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    only = sys.argv[1:] or ["mr", "pairs", "trend", "orb"]
    jobs = {
        "mr": (mr_job, [(m, tf, f) for m in MR_MARKETS for tf in ("15min", "1h") for f in MR_GRID]),
        "pairs": (pairs_job, [(p, tf, L, c) for p in PAIRS for tf in ("15min", "1h") for L in (5, 20, 60)
                              for c in (None, -2.9, -3.4)]),
        "trend": (trend_job, [(m, tf) for m in ("GBPJPY", "USDJPY", "EURGBP", "AUDUSD") for tf in ("1h", "4h", "1D")]),
        "orb": (orb_job, ["GBPJPY", "GBPUSD", "EURGBP", "EURUSD", "USDJPY"]),
    }
    with ProcessPoolExecutor(4) as ex:
        for name in only:
            fn, js = jobs[name]
            rows = [r for rs in ex.map(fn, js) for r in rs]
            pd.DataFrame(rows).to_csv(OUT / f"{name}.csv", index=False)
            print(name, len(rows), flush=True)


if __name__ == "__main__":
    main()
