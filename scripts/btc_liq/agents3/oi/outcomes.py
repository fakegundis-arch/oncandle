"""Precompute per-signal outcomes (both directions, every exit setting) for the candidate pool, real and day-shifted
(luck check).  usage: python outcomes.py <mode> <delay> <seed>   (seed 0 = real times, k>0 = shifted by +-1..14 days)"""
import itertools
import os
import sys
import time

import numpy as np
import pandas as pd

import lab

HERE = lab.HERE
STOPS = [4, 6, 8, 12, 16, 24, 32]
TPS = [1.0, 1.5, 2.0, 3.0, np.nan]
HOLDS = [300, 600, 1200, 1800, 3600, 7200]
TRAILS = [(np.nan, np.nan), (1.0, 1.0), (0.5, np.nan), (1.0, 0.5)]
EXITS = list(itertools.product(range(len(STOPS)), TPS, HOLDS, TRAILS))
A, B = lab.bc.ts_of("2026-01-01"), lab.bc.ts_of("2026-07-01")


def pool_of(F):
    m = ((F.d5 <= -0.001) | (F.d10 <= -0.002) | (F.d15 <= -0.0025) | (F.d30 <= -0.004) | (F.z5_7d <= -2)
         | (F.d5 >= 0.0015))
    return m & (F.s >= A) & (F.s < B) & F.vol.notna()


def shifted_times(s, seed):
    rng = np.random.default_rng(seed)
    k = rng.integers(1, 15, len(s)) * rng.choice([-1, 1], len(s))
    t = s + k * 86400
    bad = (t < A) | (t >= B - 7200)
    t[bad] = s[bad] - k[bad] * 86400
    return t


if __name__ == "__main__":
    mode, delay, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    F = pd.read_parquet(os.path.join(HERE, f"feat_{mode}_d{delay}.parquet"))
    P = F[pool_of(F)].reset_index(drop=True)
    s = P.s.to_numpy(np.int64)
    if seed:
        s = shifted_times(s, seed)
        # vol at the shifted time (the fake signal's own stop scale)
        Fi = F.set_index("s")
        vol = Fi.vol.reindex(s).to_numpy()
    else:
        vol = P.vol.to_numpy()
    ex = lab.Ex()
    n = len(P)
    t = time.time()
    ent = np.zeros((n, 2), np.int64)
    px = np.zeros((n, 2))
    sd = np.zeros((len(STOPS), n))
    R = np.full((len(EXITS), n, 2), np.nan, np.float32)
    X = np.zeros((len(EXITS), n, 2), np.int32)
    for di, d in enumerate((-1, 1)):
        for j, (ki, tp, hold, (be, tr)) in enumerate(EXITS):
            e_, x_, r_, sd_, px_ = ex.run(s, d, STOPS[ki] * vol, tp, hold, be, tr)
            R[j, :, di] = r_
            X[j, :, di] = (x_ - A).astype(np.int32)
            if j == 0:
                ent[:, di], px[:, di] = e_, px_
            sd[ki] = np.where(sd_ > 0, sd_, sd[ki])
    print("outcomes", n, time.time() - t)
    np.savez(os.path.join(HERE, f"out_{mode}_d{delay}_s{seed}.npz"), R=R, X=X, ent=ent, px=px, sd=sd, sig=s,
             row=P.index.to_numpy(), ct=P.ct.to_numpy())
