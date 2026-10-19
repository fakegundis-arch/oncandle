#!/usr/bin/env python3
"""Gold Asian breakout v18 search: three engines from v5 and v13, chosen on 2026 ONLY (see scripts/gold_v18.py).

Engines side by side (own position each, risk = % of equity at entry), every trade charged Exness's measured $0.25:
  E1 v5 Asian      : v5 unchanged (max 2/day, weekly stop -2R); sells at s1 x the risk
  E2 v13 Asian     : v10 rules + break-even / target variants + quiet-market skip, equity-curve filter 10 trades / -2R
  E3 v13 New York  : 12-15 Donchian 15, exit variants + quiet-market skip, same filter
Overlays are tie-free: the equity filter skips a trade only when the last 10 paper trades sum to less than -2R - 1e-9,
and the weekly stop fires once the week's real trades reach -2R + 1e-9, so two full losses (-1R +/- 1e-14 each) always
count as -2R. Account level: no new trades after `dl` losing trades in a UTC day (a count, so no rounding tie).
No percentage daily stop: at any value that equals a sum of engine risks it is decided by rounding (v17's lesson).

Results: 2026 (full, Jan-May, Jun-Oct) -> results/gold/v18_search.npz (the only file the selection reads);
2025 and Q4 2024 -> results/gold/v18_sealed.npz (opened once, by `gold_v18.py --reveal`).
    python scripts/gold_v18_search.py
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
import gold_portfolio_sim as S  # noqa: E402

COST = dict(cost=0.25)
EPS = 1e-9
SEL = {"y26": ("2026-01-01", "2026-11-01"), "h1": ("2026-01-01", "2026-06-01"), "h2": ("2026-06-01", "2026-11-01")}
SEALED = {"y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}
OUT, OUT_SEALED = ROOT / "results/gold/v18_search.npz", ROOT / "results/gold/v18_sealed.npz"

E2_EXIT = {"1.0/0.3": (1.0, 0.3), "1.25/0.2": (1.25, 0.2), "1.5/0.1": (1.5, 0.1), "1.5/0.2": (1.5, 0.2),
           "1.5/0.3": (1.5, 0.3), "1.75/0.1": (1.75, 0.1), "1.75/0.2": (1.75, 0.2)}
E3_EXIT = {"base": dict(be=1.0, be_buf=0.3, rr=4.0, stop_atr=1.5), "A": dict(be=0.75, be_buf=0.0, rr=3.0, stop_atr=1.25),
           "C": dict(be=0.75, be_buf=0.1, rr=3.0, stop_atr=1.25), "D": dict(be=0.6, be_buf=0.0, rr=3.0, stop_atr=1.25),
           "B": dict(be=0.6, be_buf=0.1, rr=2.5, stop_atr=1.5)}
VAR = dict(e2_exit=list(E2_EXIT), e2_rr=[4.0, 4.5], e2_floor=[0.0, 0.11, 0.12, 0.13, 0.14],
           e3_exit=list(E3_EXIT), e3_floor=[0.0, 0.12])
RISK = dict(w1=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08], s1=[1.0, 0.5],
            w2=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08], w3=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            dl=[0, 2, 3])
DIMS = {**VAR, **RISK}


def overlay(t, eq_n, eq_thr, week_cap, skip):
    """Equity-curve filter on paper trades (all signals), then the quiet-market skip, then the weekly stop on the real
    trades that remain; both thresholds with a 1e-9 margin so exact -2R sums are decided the same way every time."""
    r = t.r.to_numpy()
    take = np.ones(len(t), bool)
    if eq_n > 0:
        for i in range(eq_n, len(r)):
            if np.sum(r[i - eq_n:i]) < eq_thr - EPS:
                take[i] = False
    take &= ~skip
    if week_cap < 0:
        wk = t.entry_time.dt.isocalendar()
        key = (wk.year * 100 + wk.week).to_numpy()
        run, cur = 0.0, None
        for i in range(len(r)):
            if key[i] != cur:
                cur, run = key[i], 0.0
            if run <= week_cap + EPS:
                take[i] = False
            elif take[i]:
                run += r[i]
    return t[take]


def quiet(t, m15, floor):
    """True where the signal bar's ATR(14) is below `floor` % of its close (bar = the M15 bar before the entry)."""
    if floor <= 0:
        return np.zeros(len(t), bool)
    a = (ind.atr(m15, 14) / m15.close * 100).reindex(t.entry_time - pd.Timedelta("15min")).to_numpy()
    return np.nan_to_num(a, nan=1.0) < floor


def e1(m1, m15):
    t = G.backtest(m1, m15, replace(V5, **COST))
    return overlay(t, 0, 0.0, -2.0, np.zeros(len(t), bool))


def e2(m1, m15, ex, rr, floor):
    b, buf = E2_EXIT[ex]
    t = G.backtest(m1, m15, replace(V10, be=b, be_buf=buf, rr=rr, **COST))
    return overlay(t, 10, -2.0, -2.0, quiet(t, m15, floor))


def e3(m1, m15, ex, floor):
    t = G.backtest(m1, m15, replace(NY, **E3_EXIT[ex], **COST))
    return overlay(t, 10, -2.0, -2.0, quiet(t, m15, floor))


def mixes():
    rows = list(itertools.product(*RISK.values()))
    W = np.array([[r[0], r[2], r[3]] for r in rows], float)
    SM = np.ones_like(W); SM[:, 0] = [r[1] for r in rows]
    return W, SM, np.zeros(len(rows)), np.zeros(len(rows)), np.array([r[4] for r in rows], np.int64)


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


def engine_set(e):
    """Engine-set index -> its settings dict (row-major over VAR)."""
    return dict(zip(VAR, [v[i] for v, i in zip(VAR.values(), np.unravel_index(e, [len(v) for v in VAR.values()]))]))


def job(v):
    t = trades_for(dict(zip(VAR, v)))
    return {k: S.run(S.prepare(t, a, b), *_S["mix"]) for k, (a, b) in {**SEL, **SEALED}.items()}


def main():
    jobs = list(itertools.product(*VAR.values()))
    n_mix = len(mixes()[0])
    per = {**SEL, **SEALED}
    res = {f"{k}_{m}": np.empty((len(jobs), n_mix), np.float32) for k in per for m in ("usd", "dd", "up", "worst")}
    print(len(jobs), "engine sets x", n_mix, "risk mixes =", f"{len(jobs) * n_mix:,}", "combinations", flush=True)
    with ProcessPoolExecutor(4, initializer=init) as ex:
        for i, out in enumerate(ex.map(job, jobs, chunksize=4)):
            for k, (fin, dd, up, worst) in out.items():
                res[f"{k}_usd"][i], res[f"{k}_dd"][i], res[f"{k}_up"][i], res[f"{k}_worst"][i] = fin * 1000, dd, up, worst
            if i % 100 == 0:
                print(i, "/", len(jobs), flush=True)
    shape = np.array([len(x) for x in VAR.values()] + [len(x) for x in RISK.values()])
    np.savez_compressed(OUT, shape=shape, **{k: v for k, v in res.items() if k.split("_")[0] in SEL})
    np.savez_compressed(OUT_SEALED, shape=shape, **{k: v for k, v in res.items() if k.split("_")[0] in SEALED})
    print(len(jobs) * n_mix, "combinations; 2026 ->", OUT.name, "| 2025 and Q4 2024 sealed ->", OUT_SEALED.name)


if __name__ == "__main__":
    main()
