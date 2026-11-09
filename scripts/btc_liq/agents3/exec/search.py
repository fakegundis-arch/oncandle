"""stage A: market entry, vol stop, exit grid x signal masks x maxpos.  Same code runs on real and fake signals.

usage: python search.py real|fakeK   -> resA_<tag>.parquet
"""
import itertools
import sys
import time

import numba as nb
import numpy as np
import pandas as pd

import lab
from lab import bc
from engine import JAN, MAY, JUL, APR

MAR = bc.ts_of("2026-03-01")

STOPS = [1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
HOLDS = [120, 180, 240, 300, 420, 600, 900]
TPS = [np.nan, 1.0, 1.5, 2.0, 3.0, 4.0]
BTS = [(np.nan, np.nan), (0.5, np.nan), (1.0, np.nan), (1.5, np.nan), (0.5, 0.5), (0.5, 1.0), (1.0, 0.5), (1.0, 1.0),
       (1.0, 1.5), (1.5, 1.0), (1.5, 1.5), (2.0, 1.0)]
DOIS = [-0.0015, -0.002, -0.0025, -0.003, -0.004, -0.005, -0.007]
MVS = [0.001, 0.0015, 0.002, 0.0025, 0.003, 0.004]
NETS = [0, 1]
COSTS = [np.inf, 1.0, 0.75]
MAXPOS = [1, 2, 3]


def settings():
    return list(itertools.product(STOPS, HOLDS, TPS, BTS))


def masks(f):
    out, keys = [], []
    for a, b, c, e in itertools.product(DOIS, MVS, NETS, COSTS):
        m = (f.doi <= a) & (f.mv_abs >= b) & (f.cost <= e)
        if c:
            m &= f.net > 0
        out.append(m.to_numpy())
        keys.append((a, b, c, e))
    return np.array(out), keys


@nb.njit(cache=True)
def _acc(ent, ext, rr, sds, pxs, idx, maxpos, start, end, mid):
    """account over idx (sorted by entry) -> n, R, gw, gl, final, dd, R before mid, R from mid"""
    bal, peak, dd = 1000.0, 1000.0, 0.0
    o_on = np.zeros(8, np.bool_)
    o_exit = np.zeros(8, np.int64)
    o_lot = np.zeros(8)
    o_sd = np.zeros(8)
    o_r = np.zeros(8)
    n = 0
    R = gw = gl = R1 = R2 = 0.0
    m = len(idx)
    for q in range(m + 1):
        last = q == m
        if not last:
            e = idx[q]
            if np.isnan(rr[e]) or ent[e] < start or ent[e] >= end:
                continue
            te = ent[e]
        else:
            te = 0
        while True:
            best, bk = -1, 0
            for s in range(8):
                if o_on[s] and (last or o_exit[s] <= te) and (best < 0 or o_exit[s] < best):
                    best, bk = o_exit[s], s
            if best < 0:
                break
            bal = bal + o_lot[bk] * o_sd[bk] * o_r[bk]
            if bal <= 0.01:
                bal = 0.0
            o_on[bk] = False
            peak = max(peak, bal)
            if peak > 0:
                dd = min(dd, bal / peak - 1)
        if last:
            break
        cnt, ro = 0, 0.0
        for s in range(8):
            if o_on[s]:
                cnt += 1
                ro += o_lot[s] * o_sd[s]
        if cnt >= maxpos or bal <= 0:
            continue
        st = 0.1 * bal
        if ro + st > 0.3 * bal + 1e-9:
            continue
        lot = min(st / sds[e], 100.0 * bal / pxs[e])
        for s in range(8):
            if not o_on[s]:
                o_on[s], o_exit[s], o_lot[s], o_sd[s], o_r[s] = True, ext[e], lot, sds[e], rr[e]
                break
        n += 1
        R += rr[e]
        if rr[e] > 0:
            gw += rr[e]
        else:
            gl -= rr[e]
        if te < mid:
            R1 += rr[e]
        else:
            R2 += rr[e]
    return n, R, gw, gl, bal, dd, R1, R2


@nb.njit(cache=True)
def run_all(ENT, EXT, RR, SD, PX, order, M, maxposs, p):
    """all masks x settings x maxpos -> out[k, :] ; p = (JAN, MAR, MAY, JUL)"""
    S = ENT.shape[0]
    NM = M.shape[0]
    NP = len(maxposs)
    out = np.zeros((NM * S * NP, 14))
    for mi in range(NM):
        for s in range(S):
            o = order[s]
            sel = o[M[mi][o]]
            for pi in range(NP):
                mp = maxposs[pi]
                a = _acc(ENT[s], EXT[s], RR[s], SD[s], PX[s], sel, mp, p[0], p[2], p[1])
                b = _acc(ENT[s], EXT[s], RR[s], SD[s], PX[s], sel, mp, p[2], p[3], p[3])
                k = (mi * S + s) * NP + pi
                out[k, 0] = a[0]
                out[k, 1] = a[1]
                out[k, 2] = a[2] / a[3] if a[3] > 0 else 99.0
                out[k, 3] = a[4]
                out[k, 4] = a[5]
                out[k, 5] = a[6]
                out[k, 6] = a[7]
                out[k, 7] = b[0]
                out[k, 8] = b[1]
                out[k, 9] = b[2] / b[3] if b[3] > 0 else 99.0
                out[k, 10] = b[4]
                out[k, 11] = b[5]
                out[k, 12] = mi
                out[k, 13] = s
    return out


def load_signals(tag, L=None):
    f = pd.read_parquet("sig_all.parquet")
    f = f[(f.doi <= max(DOIS)) & (f.mv_abs >= min(MVS))].sort_values("dec").reset_index(drop=True)
    if tag != "real":
        f = fake_shift(L, f, int(tag[4:]))
    f["cost"] = 2 * f.spread / f.vol
    return f


def fake_shift(L, f, seed):
    """move each signal by a random 1-14 days (sign chosen to stay inside Jan-Jun), same direction; context
    features (vol, spread, swing, ...) re-measured at the new time; signal features (doi, mv, net) kept."""
    import features
    rng = np.random.default_rng(seed)
    days = rng.integers(1, 15, len(f))
    sgn = rng.choice([-1, 1], len(f))
    dec = f.dec.to_numpy()
    new = dec + sgn * days * 86400
    bad = (new < JAN + 2 * 3600) | (new >= JUL - 3600)
    new[bad] = dec[bad] - sgn[bad] * days[bad] * 86400
    ctx = context(L, new)
    g = f.copy()
    g["dec"] = new
    g["T"] = new - 60
    for c in ctx:
        g[c] = ctx[c]
    return g.sort_values("dec").reset_index(drop=True)


def context(L, dec):
    T_ = L.tk["t"]
    q = np.searchsorted(T_, dec) - 1
    out = {"vol": L.vol_at(dec), "spread": L.tk["ask_last"][q] - L.tk["bid_last"][q],
           "hour": pd.to_datetime(dec, unit="s").hour.to_numpy()}
    return out


def main(tag):
    t = time.time()
    L = lab.Lab()
    f = load_signals(tag, L)
    f.to_parquet(f"sigs_{tag}.parquet")
    sig, d, vol = f.dec.to_numpy(), f.dir.to_numpy(), f.vol.to_numpy()
    ST = settings()
    S, N = len(ST), len(f)
    ENT = np.zeros((S, N), np.int64)
    EXT = np.zeros((S, N), np.int64)
    RR = np.zeros((S, N))
    SD = np.zeros((S, N))
    PX = np.zeros((S, N))
    for k, (st, h, tp, (be, tr)) in enumerate(ST):
        ENT[k], EXT[k], RR[k], SD[k], PX[k] = L.nbt(sig, d, 0, 0.0, 0, st * vol, tp, h, be, tr)
    print(tag, "signals", N, "settings", S, "outcomes", round(time.time() - t, 1), flush=True)
    del L
    order = np.argsort(np.where(np.isnan(RR), 2 ** 62, ENT), axis=1, kind="stable")
    M, keys = masks(f)
    out = run_all(ENT, EXT, RR, SD, PX, order, M, np.array(MAXPOS), np.array([JAN, MAR, MAY, JUL]))
    print("accounts", round(time.time() - t, 1), flush=True)
    res = pd.DataFrame(out[:, :12], columns=["nA", "RA", "pfA", "fA", "ddA", "RA1", "RA2", "nB", "RB", "pfB", "fB", "ddB"])
    mi, si = out[:, 12].astype(int), out[:, 13].astype(int)
    kk = np.array(keys, dtype=float)
    res["doi"], res["mv"], res["net"], res["cost"] = kk[mi, 0], kk[mi, 1], kk[mi, 2], kk[mi, 3]
    ss = np.array([(a, b, c, e[0], e[1]) for a, b, c, e in ST], dtype=float)
    res["stop"], res["hold"], res["tp"], res["be"], res["tr"] = ss[si, 0], ss[si, 1], ss[si, 2], ss[si, 3], ss[si, 4]
    res["mp"] = np.tile(MAXPOS, len(out) // len(MAXPOS))
    for c in res.columns:
        if res[c].dtype == np.float64 and c not in ("fA", "fB"):
            res[c] = res[c].astype(np.float32)
    res.to_parquet(f"resA_{tag}.parquet")
    np.savez_compressed(f"outA_{tag}.npz", ENT=ENT, EXT=EXT, RR=RR.astype(np.float32), SD=SD.astype(np.float32),
                        PX=PX.astype(np.float32)) if tag == "real" else None
    print("done", round(time.time() - t, 1), len(res), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
