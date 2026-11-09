"""stage B: multi-bucket open-interest drops (5 / 10 / 15 min windows, honest timing) with longer holds.
usage: python search2.py real|fakeK -> resB_<tag>.parquet"""
import itertools
import sys
import time

import numpy as np
import pandas as pd

import lab
from lab import bc
from engine import JAN, MAY, JUL, APR
from search import run_all, fake_shift, MAR

SIDES = [1, -1]
ENTRIES = [(0, 0.0, 0), (1, 1.0, 1200), (1, 2.0, 1200), (1, 4.0, 1200)]
STOPS = [5, 8, 12, 20]
HOLDS = [1800, 3600, 7200, 14400]
TPS = [np.nan, 2.0, 4.0]
BTS = [(np.nan, np.nan), (1.0, np.nan)]
WS = [1, 2, 3]
DOIS = [-0.003, -0.005, -0.007, -0.01, -0.015]
MVS = [0.002, 0.004, 0.006, 0.01]
MAXPOS = [1, 3]


def settings():
    return list(itertools.product(SIDES, ENTRIES, STOPS, HOLDS, TPS, BTS))


def build_signals(L):
    """one row per (5-min row, window w) that meets the loosest thresholds; dir = sign of the window move."""
    m = L.metrics
    ts = m.ts.to_numpy()
    s_oi = pd.Series(m.sum_open_interest.to_numpy(), index=ts)
    full = np.arange(ts[0], ts[-1] + 1, 300)
    s_oi = s_oi.reindex(full)
    known = full + 360
    end = full + 300 - L.t0
    px = lambda k: L.c[np.clip(k, 0, L.n - 1)]
    out = []
    for w in WS:
        doi = (s_oi / s_oi.shift(w) - 1).to_numpy()
        mv = px(end) / px(end - 300 * w) - 1
        sel = (doi <= max(DOIS)) & (np.abs(mv) >= min(MVS)) & (known >= JAN) & (known < JUL - 3600)
        out.append(pd.DataFrame(dict(dec=known[sel], dir=np.sign(mv[sel]).astype(int), doi=doi[sel],
                                     mv_abs=np.abs(mv[sel]), w=w)))
    f = pd.concat(out).sort_values(["dec", "w"]).reset_index(drop=True)
    from search import context
    ctx = context(L, f.dec.to_numpy())
    for c in ctx:
        f[c] = ctx[c]
    f["net"] = 0.0
    f["T"] = f.dec - 60
    return f


def masks(f):
    out, keys = [], []
    for w, a, b in itertools.product(WS, DOIS, MVS):
        out.append(((f.w == w) & (f.doi <= a) & (f.mv_abs >= b)).to_numpy())
        keys.append((w, a, b))
    return np.array(out), keys


def main(tag):
    t = time.time()
    L = lab.Lab()
    f = build_signals(L)
    if tag != "real":
        f = fake_shift(L, f, 100 + int(tag[4:]))
    f = f[~np.isnan(f.vol)].reset_index(drop=True)
    sig, d, vol = f.dec.to_numpy(), f.dir.to_numpy(), f.vol.to_numpy()
    ST = settings()
    S, N = len(ST), len(f)
    ENT = np.zeros((S, N), np.int64)
    EXT = np.zeros((S, N), np.int64)
    RR = np.zeros((S, N))
    SD = np.zeros((S, N))
    PX = np.zeros((S, N))
    for k, (side, (kind, off, life), st, h, tp, (be, tr)) in enumerate(ST):
        ENT[k], EXT[k], RR[k], SD[k], PX[k] = L.nbt(sig, side * d, kind, off * vol, life, st * vol, tp, h, be, tr)
    print(tag, "signals", N, "settings", S, "outcomes", round(time.time() - t, 1), flush=True)
    del L
    order = np.argsort(np.where(np.isnan(RR), 2 ** 62, ENT), axis=1, kind="stable")
    M, keys = masks(f)
    out = run_all(ENT, EXT, RR, SD, PX, order, M, np.array(MAXPOS), np.array([JAN, MAR, MAY, JUL, APR]))
    res = pd.DataFrame(out[:, :12], columns=["nA", "RA", "pfA", "fA", "ddA", "RA1", "RA2", "n", "R", "pf", "final", "dd"])
    res["R1"], res["R2"] = out[:, 14], out[:, 15]
    res["mi"], res["si"] = out[:, 12].astype(np.int32), out[:, 13].astype(np.int32)
    res["mp"] = np.tile(MAXPOS, len(out) // len(MAXPOS)).astype(np.int8)
    res.to_parquet(f"resB_{tag}.parquet")
    print("done", round(time.time() - t, 1), len(res), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
