#!/usr/bin/env python3
"""Gold Asian breakout v17 search: engines from v5 and v13 (plus extras from the 2026 study), each engine's settings
and risk, and two account-level rules (open-risk cap, daily stop), every trade charged Exness's measured spread $0.25.
ONE rule set for every month. Results stored for 2026 (selection), 2025 and Q4 2024 (test, not printed).
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
from backtester import gold as G  # noqa: E402
from gold_v3 import overlay  # noqa: E402
from gold_versions import NY, V5, V10  # noqa: E402
import gold_v17_sim as S  # noqa: E402

COST = dict(cost=0.25)
PER = {"y26": ("2026-01-01", "2026-11-01"), "y25": ("2025-01-01", "2026-01-01"), "q4": ("2024-10-01", "2025-01-01")}
OUT = ROOT / "results/gold/v17_search.npz"
EQ = {"off": (0, 0.0, -2.0), "10/-2": (10, -2.0, -2.0), "20/-3": (20, -3.0, -2.0), "10/-2 w-3": (10, -2.0, -3.0)}

# ---- engine variants: name -> (base settings, changes, overlay key). Filled from the 2026 study.
E1 = {}   # v5-style Asian engine
E2 = {}   # v13 Asian engine
E3 = {}   # v13 New York engine
ENGINES = [E1, E2, E3]
# ---- risk and account-level rules
RISK = dict(w1=[], sm1=[], w2=[], sm2=[], w3=[], cap=[], dst=[])


def build(spec, m1, m15):
    base, ch, ov = spec
    return overlay(G.backtest(m1, m15, replace(base, **ch, **COST)), *EQ[ov])


def mixes():
    rows = list(itertools.product(*RISK.values()))
    W = np.array([[r[0], r[2], r[4]] for r in rows], float)
    SM = np.array([[r[1], r[3], 1.0] for r in rows], float)
    CAP = np.array([r[5] for r in rows], float)
    DST = np.array([r[6] for r in rows], float)
    return W, SM, CAP, DST


_S: dict = {}


def init():
    m1, m15 = G.data(ROOT)
    _S["streams"] = [{k: build(v, m1, m15) for k, v in E.items()} for E in ENGINES]
    _S["mix"] = mixes()


def job(names):
    if not _S:
        init()
    t = pd.concat([_S["streams"][k][nm].assign(eng=k) for k, nm in enumerate(names)], ignore_index=True)
    W, SM, CAP, DST = _S["mix"]
    out = {}
    for k, (a, b) in PER.items():
        out[k] = S.run(S.prepare(t, a, b), W, SM, CAP, DST)
    return out


def main():
    jobs = list(itertools.product(*[list(E) for E in ENGINES]))
    W = mixes()[0]
    res = {f"{k}_{m}": np.empty((len(jobs), len(W)), np.float32) for k in PER for m in ("usd", "dd", "up", "worst")}
    with ProcessPoolExecutor(4, initializer=init) as ex:
        for i, out in enumerate(ex.map(job, jobs, chunksize=4)):
            for k, (fin, dd, up, worst) in out.items():
                res[f"{k}_usd"][i], res[f"{k}_dd"][i], res[f"{k}_up"][i], res[f"{k}_worst"][i] = fin * 1000, dd, up, worst
            if i % 64 == 0:
                print(i, "/", len(jobs), flush=True)
    shape = [len(E) for E in ENGINES] + [len(v) for v in RISK.values()]
    np.savez_compressed(OUT, shape=np.array(shape), **res)
    print(len(jobs) * len(W), "combinations")


if __name__ == "__main__":
    main()
