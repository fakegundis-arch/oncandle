#!/usr/bin/env python3
"""Gold Asian breakout v16 search: v5's and v13's engines (plus a London engine) blended into ONE bot, every trade
charged Exness's measured XAUUSDm spread ($0.25), ONE rule set for every month.

Engines (each with its own position; risk = % of equity at entry):
  E1 v5 Asia      : Donchian 10, EMA400 rising vs 16 bars, previous-day break, 00-06, no daily-trend filter
  E2 v13 Asia     : E1 + daily trend (D1 EMA20) + regime filter + equity-curve filter
  E3 v13 New York : E2 rules on 12-15, Donchian 15
  E4 London       : E2 rules on 07-09
Every engine setting and every risk mix is booked for Q4 2024, 2025 and 2026 (2,211,840 combinations).
Chosen on 2026 only (rule in scripts/gold_v16.py); 2025 and Q4 2024 are the test.
    python scripts/gold_v16_search.py  -> results/gold/v16_search.npz
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
from backtester.engine import njit  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_versions import NY, V5, V10  # noqa: E402

COST = dict(cost=0.25)
BE = {"1.0/0.3": (1.0, 0.3), "1.5/0.3": (1.5, 0.3), "1.5/0.5": (1.5, 0.5)}
EQ = {"off": (0, 0.0, -2.0), "10/-2": (10, -2.0, -2.0), "20/-3": (20, -3.0, -2.0)}
# engine-setting dimensions (order matters for the result tensor)
VAR = dict(e1_mpd=[2, 99], e1_eq=["off", "10/-2"], e1_be=["1.0/0.3", "1.5/0.5"],
           e2_be=["1.0/0.3", "1.5/0.3", "1.5/0.5"], e2_atr=[0.0, 0.08], e2_eq=["10/-2", "20/-3"],
           e3_be=["1.0/0.3", "1.5/0.5"], e3_eq=["10/-2", "20/-3"],
           e4_don=[15, 20], e4_rr=[3.0, 4.0])
# risk dimensions
RISK = dict(w1=[0.0, 0.03, 0.06, 0.09, 0.12], sm1=[1.0, 0.5], w2=[0.0, 0.03, 0.06, 0.09, 0.12, 0.14], sm2=[1.0, 0.5],
            w3=[0.0, 0.02, 0.04, 0.06], w4=[0.0, 0.02, 0.04])
PER = {"y26": ("2026-01-01", "2026-11-01"), "y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}
OUT = ROOT / "results/gold/v16_search.npz"


def e1(m1, m15, mpd, eq, be):
    b, buf = BE[be]
    return overlay(G.backtest(m1, m15, replace(V5, max_per_day=mpd, be=b, be_buf=buf, **COST)), *EQ[eq])


def e2(m1, m15, be, atr, eq):
    b, buf = BE[be]
    return overlay(G.backtest(m1, m15, replace(V10, be=b, be_buf=buf, atr_pct_min=atr, **COST)), *EQ[eq])


def e3(m1, m15, be, eq):
    b, buf = BE[be]
    return overlay(G.backtest(m1, m15, replace(NY, be=b, be_buf=buf, **COST)), *EQ[eq])


def e4(m1, m15, don, rr):
    return overlay(G.backtest(m1, m15, replace(V10, ses_start=7, ses_end=9, don=don, rr=rr, **COST)), *EQ["10/-2"])


@njit(cache=True)
def sim_many(order, n, r, eng, short, mon, n_mon, W, SM):
    """Book every risk mix in W (n_mix x 4 engines; SM = short multipliers) over one period's events.
    order: event order (index < n = entry of trade i, >= n = exit of trade i - n). Returns final multiple, max drawdown,
    months up, worst month for each mix."""
    n_mix = W.shape[0]
    fin = np.empty(n_mix); mdd = np.empty(n_mix); up = np.empty(n_mix, np.int64); worst = np.empty(n_mix)
    stake = np.empty(n)
    mon_eq = np.empty(n_mon)
    for w in range(n_mix):
        eq = 1.0; peak = 1.0; dd = 0.0
        for m in range(n_mon):
            mon_eq[m] = -1.0
        for o in order:
            if o < n:
                f = W[w, eng[o]]
                if short[o]:
                    f *= SM[w, eng[o]]
                stake[o] = f * eq
            else:
                i = o - n
                eq = eq + stake[i] * r[i]
                if eq < 0.0:
                    eq = 0.0
                if eq > peak:
                    peak = eq
                if peak > 0 and eq / peak - 1.0 < dd:
                    dd = eq / peak - 1.0
                mon_eq[mon[i]] = eq
        prev = 1.0; u = 0; wr = 0.0
        for m in range(n_mon):
            v = mon_eq[m] if mon_eq[m] >= 0 else prev
            ret = v / prev - 1.0 if prev > 0 else 0.0
            if ret > 0:
                u += 1
            if ret < wr:
                wr = ret
            prev = v
        fin[w] = eq; mdd[w] = dd; up[w] = u; worst[w] = wr
    return fin, mdd, up, worst


def mixes():
    rows = list(itertools.product(*RISK.values()))
    W = np.array([[r[0], r[2], r[4], r[5]] for r in rows])
    SM = np.array([[r[1], r[3], 1.0, 1.0] for r in rows])
    return W, SM


_S: dict = {}


def init():
    m1, m15 = G.data(ROOT)
    _S["e1"] = {k: e1(m1, m15, *k) for k in itertools.product(VAR["e1_mpd"], VAR["e1_eq"], VAR["e1_be"])}
    _S["e2"] = {k: e2(m1, m15, *k) for k in itertools.product(VAR["e2_be"], VAR["e2_atr"], VAR["e2_eq"])}
    _S["e3"] = {k: e3(m1, m15, *k) for k in itertools.product(VAR["e3_be"], VAR["e3_eq"])}
    _S["e4"] = {k: e4(m1, m15, *k) for k in itertools.product(VAR["e4_don"], VAR["e4_rr"])}
    _S["W"], _S["SM"] = mixes()


def job(v):
    if not _S:
        init()
    kw = dict(zip(VAR, v))
    parts = [_S["e1"][(kw["e1_mpd"], kw["e1_eq"], kw["e1_be"])], _S["e2"][(kw["e2_be"], kw["e2_atr"], kw["e2_eq"])],
             _S["e3"][(kw["e3_be"], kw["e3_eq"])], _S["e4"][(kw["e4_don"], kw["e4_rr"])]]
    t = pd.concat([p.assign(eng=k) for k, p in enumerate(parts)], ignore_index=True)
    out = {}
    for k, (a, b) in PER.items():
        x = t[(t.entry_time >= a) & (t.entry_time < b)].reset_index(drop=True)
        months = pd.period_range(a, pd.Timestamp(b) - pd.Timedelta("1D"), freq="M")
        n = len(x)
        tin = x.entry_time.to_numpy("datetime64[m]").astype(np.int64)
        tout = x.exit_time.to_numpy("datetime64[m]").astype(np.int64)
        order = np.argsort(np.concatenate((tin * 2, tout * 2 + 1)), kind="mergesort")
        mon = months.get_indexer(x.exit_time.dt.to_period("M").clip(upper=months[-1])).astype(np.int64)
        fin, dd, up, worst = sim_many(order.astype(np.int64), n, x.r.to_numpy(np.float64), x.eng.to_numpy(np.int64),
                                      (x.dir.to_numpy() == -1), mon, len(months), _S["W"], _S["SM"])
        out[k] = (fin * 1000, dd, up, worst)
    return out


def main():
    jobs = list(itertools.product(*VAR.values()))
    W, _ = mixes()
    shape_v = [len(x) for x in VAR.values()]
    res = {f"{k}_{m}": np.empty((len(jobs), len(W)), np.float32) for k in PER for m in ("usd", "dd", "up", "worst")}
    with ProcessPoolExecutor(4, initializer=init) as ex:
        for i, out in enumerate(ex.map(job, jobs, chunksize=8)):
            for k, (fin, dd, up, worst) in out.items():
                res[f"{k}_usd"][i], res[f"{k}_dd"][i], res[f"{k}_up"][i], res[f"{k}_worst"][i] = fin, dd, up, worst
            if i % 128 == 0:
                print(i, "/", len(jobs), flush=True)
    np.savez_compressed(OUT, shape=np.array(shape_v + [len(x) for x in RISK.values()]), **res)
    print(len(jobs) * len(W), "combinations")


if __name__ == "__main__":
    main()
