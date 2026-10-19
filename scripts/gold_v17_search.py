#!/usr/bin/env python3
"""Gold Asian breakout v17 search, built on the 2026 study of v5 and v13 (2026 data only; 2025 untouched).

Engines side by side (own position each, risk = % of equity at entry), every trade charged Exness's measured $0.25:
  E1 v5 Asian sleeve : v5 unchanged (max 2/day, weekly stop -2R)
  E2 v13 Asian       : v10 rules + break-even / target from the study + quiet-market skip
  E3 v13 New York    : 12-15 Donchian 15, exits from the study + quiet-market skip
Quiet-market skip: no REAL trade when the signal bar's ATR(14) is below `floor` % of price; the signal still counts as a
paper trade for the engine's equity-curve filter, and skipped trades do not count toward the weekly stop.
Account level: daily stop after `dst_k` x the Asian risk of the day's loss, and no new trades after `dl` losing trades
in a UTC day. ONE rule set for every month. Results for 2026 (selection), 2025 and Q4 2024 (test, not printed).
    python scripts/gold_v17_search.py  -> results/gold/v17_search.npz
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
from backtester import gold as G, indicators as ind  # noqa: E402
from gold_versions import NY, V5, V10  # noqa: E402
import gold_v17_sim as S  # noqa: E402

COST = dict(cost=0.25)
PER = {"y26": ("2026-01-01", "2026-11-01"), "y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}
OUT = ROOT / "results/gold/v17_search.npz"

E2_EXIT = {"1.0/0.3": (1.0, 0.3), "1.25/0.2": (1.25, 0.2), "1.5/0.1": (1.5, 0.1), "1.5/0.2": (1.5, 0.2),
           "1.5/0.3": (1.5, 0.3), "1.75/0.1": (1.75, 0.1), "1.75/0.2": (1.75, 0.2)}
E3_EXIT = {"base": dict(be=1.0, be_buf=0.3, rr=4.0, stop_atr=1.5), "A": dict(be=0.75, be_buf=0.0, rr=3.0, stop_atr=1.25),
           "C": dict(be=0.75, be_buf=0.1, rr=3.0, stop_atr=1.25), "D": dict(be=0.6, be_buf=0.0, rr=3.0, stop_atr=1.25),
           "B": dict(be=0.6, be_buf=0.1, rr=2.5, stop_atr=1.5)}
VAR = dict(e2_exit=list(E2_EXIT), e2_rr=[4.0, 4.5], e2_floor=[0.0, 0.11, 0.12, 0.13, 0.14],
           e3_exit=list(E3_EXIT), e3_floor=[0.0, 0.12])
RISK = dict(w1=[0.0, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03],
            w2=[0.03, 0.035, 0.04, 0.045, 0.05, 0.055, 0.06, 0.065, 0.07, 0.075, 0.08, 0.085, 0.09, 0.095, 0.10],
            w3=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06], dst_k=[0.0, 1.1, 1.25, 1.5, 2.0], dl=[0, 2, 3])


def overlay2(t, eq_n, eq_thr, week_cap, skip):
    """Equity-curve filter on paper trades (all signals), then the quiet-market skip, then the weekly stop on the real
    trades that remain."""
    r = t.r.to_numpy()
    take = np.ones(len(t), bool)
    if eq_n > 0:
        cs = np.concatenate([[0.0], np.cumsum(r)])
        for i in range(eq_n, len(r)):
            if cs[i] - cs[i - eq_n] < eq_thr:
                take[i] = False
    take &= ~skip
    if week_cap < 0:
        wk = t.entry_time.dt.isocalendar()
        key = (wk.year * 100 + wk.week).to_numpy()
        run, cur = 0.0, None
        for i in range(len(r)):
            if key[i] != cur:
                cur, run = key[i], 0.0
            if run <= week_cap:
                take[i] = False
            elif take[i]:
                run += r[i]
    return t[take]


def quiet(t, m15, floor):
    if floor <= 0:
        return np.zeros(len(t), bool)
    a = (ind.atr(m15, 14) / m15.close * 100).reindex(t.entry_time - pd.Timedelta("15min")).to_numpy()
    return np.nan_to_num(a, nan=1.0) < floor


def e1(m1, m15):
    t = G.backtest(m1, m15, replace(V5, **COST))
    return overlay2(t, 0, 0.0, -2.0, np.zeros(len(t), bool))


def e2(m1, m15, ex, rr, floor):
    b, buf = E2_EXIT[ex]
    t = G.backtest(m1, m15, replace(V10, be=b, be_buf=buf, rr=rr, **COST))
    return overlay2(t, 10, -2.0, -2.0, quiet(t, m15, floor))


def e3(m1, m15, ex, floor):
    t = G.backtest(m1, m15, replace(NY, **E3_EXIT[ex], **COST))
    return overlay2(t, 10, -2.0, -2.0, quiet(t, m15, floor))


def mixes():
    rows = list(itertools.product(*RISK.values()))
    W = np.array([[r[0], r[1], r[2]] for r in rows], float)
    SM = np.ones_like(W)
    CAP = np.zeros(len(rows))
    DST = np.array([r[3] * r[1] for r in rows], float)
    DL = np.array([r[4] for r in rows], np.int64)
    return W, SM, CAP, DST, DL


_S: dict = {}


def init():
    m1, m15 = G.data(ROOT)
    _S["e1"] = e1(m1, m15)
    _S["e2"] = {k: e2(m1, m15, *k) for k in itertools.product(VAR["e2_exit"], VAR["e2_rr"], VAR["e2_floor"])}
    _S["e3"] = {k: e3(m1, m15, *k) for k in itertools.product(VAR["e3_exit"], VAR["e3_floor"])}
    _S["mix"] = mixes()


def trades_for(kw):
    if not _S:
        init()
    return pd.concat([_S["e1"].assign(eng=0), _S["e2"][(kw["e2_exit"], kw["e2_rr"], kw["e2_floor"])].assign(eng=1),
                      _S["e3"][(kw["e3_exit"], kw["e3_floor"])].assign(eng=2)], ignore_index=True)


def job(v):
    t = trades_for(dict(zip(VAR, v)))
    W, SM, CAP, DST, DL = _S["mix"]
    return {k: S.run(S.prepare(t, a, b), W, SM, CAP, DST, DL) for k, (a, b) in PER.items()}


def main():
    jobs = list(itertools.product(*VAR.values()))
    n_mix = len(mixes()[0])
    res = {f"{k}_{m}": np.empty((len(jobs), n_mix), np.float32) for k in PER for m in ("usd", "dd", "up", "worst")}
    print(len(jobs), "engine sets x", n_mix, "risk mixes =", len(jobs) * n_mix, "combinations", flush=True)
    with ProcessPoolExecutor(4, initializer=init) as ex:
        for i, out in enumerate(ex.map(job, jobs, chunksize=4)):
            for k, (fin, dd, up, worst) in out.items():
                res[f"{k}_usd"][i], res[f"{k}_dd"][i], res[f"{k}_up"][i], res[f"{k}_worst"][i] = fin * 1000, dd, up, worst
            if i % 100 == 0:
                print(i, "/", len(jobs), flush=True)
    shape = [len(x) for x in VAR.values()] + [len(x) for x in RISK.values()]
    np.savez_compressed(OUT, shape=np.array(shape), **res)
    print(len(jobs) * n_mix, "combinations")


if __name__ == "__main__":
    main()
