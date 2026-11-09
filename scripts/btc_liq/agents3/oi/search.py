"""Stage-1 grid search: OI condition x move condition x direction x one extra filter x 840 exits (maxpos 1).
usage: python search.py <seed> [stage]    seed 0 = real outcomes, k = day-shifted fake outcomes."""
import os
import sys
import time

import numba as nb
import numpy as np
import pandas as pd

import lab
from outcomes import EXITS, STOPS, pool_of, A

HERE = lab.HERE
MAY, APR = lab.bc.ts_of("2026-05-01"), lab.bc.ts_of("2026-04-01")
SIGNED = ["m15", "m60", "mlag", "imb5", "ntlag", "dimb1", "dimb2", "prem", "prem60", "prem_z", "fund", "lsr_c5",
          "lsr_c60", "lsr_z7d", "tacc_c60", "tacc_z7d", "tpos_c60", "tpos_z7d", "ltaker", "tpos_c5", "tacc_c5"]
UNSIGNED = ["d5", "d10", "d15", "d30", "d60", "accel", "ndrop", "z5_7d", "z15_7d", "oi_rel7d", "oi_rel1d", "e5", "e15",
            "ez5_7d", "lsr", "tacc", "tpos", "vrel5", "rng5", "volreg", "volp", "hour", "absm5", "prem480"]
OICONDS = ([("d5", v) for v in (-0.001, -0.0015, -0.002, -0.003, -0.004, -0.005, -0.007, -0.01)]
           + [("d10", v) for v in (-0.002, -0.003, -0.004, -0.006, -0.008, -0.012)]
           + [("d15", v) for v in (-0.0025, -0.0035, -0.005, -0.007, -0.01)]
           + [("d30", v) for v in (-0.004, -0.006, -0.008, -0.012)]
           + [("z5_7d", v) for v in (-2.0, -3.0, -4.0, -6.0)]
           + [("d5up", v) for v in (0.0015, 0.0025, 0.004)])
MOVES = [("m5", v) for v in (0.0, 0.001, 0.002, 0.003, 0.005, 0.008)] + \
        [("m15", v) for v in (0.0, 0.002, 0.004, 0.007)]
QS = (0.2, 0.33, 0.5, 0.67, 0.8)


def load(seed):
    F = pd.read_parquet(os.path.join(HERE, "feat_honest_d0.parquet"))
    P = F[pool_of(F)].reset_index(drop=True)
    P["ltaker"] = np.log(P.taker)
    P["absm5"] = P.m5.abs()
    P["d5up"] = -P.d5
    O = np.load(os.path.join(HERE, f"out_honest_d0_s{seed}.npz"))
    return P, O


@nb.njit(cache=True)
def run_exits(rows, dsel, ent, px, sd, RT, XT, stop_of, base, may, apr, out):
    """rows sorted by entry time; dsel 0/1 direction index; RT/XT = (pool, 2, exits).  out[j] = metrics (COLS)."""
    nE = RT.shape[2]
    last = np.full(nE, -1, np.int64)
    st = np.zeros((nE, 17))
    for j in range(nE):
        st[j, 3] = st[j, 8] = st[j, 12] = 1000.0     # balances
        st[j, 4] = st[j, 9] = st[j, 13] = 1000.0     # peaks
    for q in range(len(rows)):
        i = rows[q]
        di = dsel[q]
        e = ent[i, di]
        p = px[i, di]
        first = e < may
        q1 = e < apr
        for j in range(nE):
            if e < last[j]:
                continue
            r = RT[i, di, j]
            if np.isnan(r):
                continue
            s = sd[stop_of[j], i]
            g = 1.0 + min(0.1, 100.0 * s / p) * r
            last[j] = XT[i, di, j] + base
            b = st[j, 12] * g
            st[j, 12] = b
            if b > st[j, 13]:
                st[j, 13] = b
            dd = b / st[j, 13] - 1
            if dd < st[j, 14]:
                st[j, 14] = dd
            if first:
                b = st[j, 3] * g
                st[j, 3] = b
                if b > st[j, 4]:
                    st[j, 4] = b
                dd = b / st[j, 4] - 1
                if dd < st[j, 5]:
                    st[j, 5] = dd
                st[j, 0] += 1
                st[j, 1] += r
                if r > 0:
                    st[j, 2] += r
                else:
                    st[j, 6] -= r
            else:
                b = st[j, 8] * g
                st[j, 8] = b
                st[j, 10] += 1
                st[j, 11] += r
                if r > 0:
                    st[j, 7] += r
                else:
                    st[j, 15] -= r
            if q1:
                st[j, 16] += r
    for j in range(nE):
        n1, R1, gw1, gl1 = st[j, 0], st[j, 1], st[j, 2], st[j, 6]
        n2, R2, gw2, gl2 = st[j, 10], st[j, 11], st[j, 7], st[j, 15]
        out[j, 0] = n1
        out[j, 1] = R1
        out[j, 2] = gw1 / gl1 if gl1 > 0 else 99.0
        out[j, 3] = st[j, 3]
        out[j, 4] = st[j, 5]
        out[j, 5] = n2
        out[j, 6] = R2
        out[j, 7] = gw2 / gl2 if gl2 > 0 else 99.0
        out[j, 8] = st[j, 8]
        out[j, 9] = n1 + n2
        out[j, 10] = R1 + R2
        out[j, 11] = (gw1 + gw2) / (gl1 + gl2) if gl1 + gl2 > 0 else 99.0
        out[j, 12] = st[j, 12]
        out[j, 13] = st[j, 14]
        out[j, 14] = st[j, 16]
        out[j, 15] = R1 + R2 - st[j, 16]
        out[j, 16] = 0.0


COLS = ["nJA", "RJA", "pfJA", "fJA", "ddJA", "nMJ", "RMJ", "pfMJ", "fMJ", "n", "R", "pf", "final", "dd", "RQ1", "RQ2",
        "x"]


def filters(P, ja):
    """extra filters: (name, feature values (signed later if needed), signed?, threshold, side)."""
    out = [("none", None, False, 0.0, 0)]
    for f in SIGNED + UNSIGNED:
        x = P[f].to_numpy(float)
        sg = f in SIGNED
        for side in (1, -1):
            for q in QS:
                # thresholds from Jan-Apr pool rows only (signed features: quantiles of |x| and of x both sides)
                base = np.abs(x[ja]) if sg else x[ja]
                th = float(np.nanquantile(base, q))
                if sg:
                    th = th if side == 1 else -th
                out.append((f, x, sg, th, side))
    return out


def main(seed, tag=""):
    P, O = load(seed)
    R, X, ent, px, sd = O["R"], O["X"], O["ent"], O["px"], O["sd"]
    RT = np.ascontiguousarray(R.transpose(1, 2, 0))
    XT = np.ascontiguousarray(X.transpose(1, 2, 0))
    del R, X
    stop_of = np.array([e[0] for e in EXITS], np.int64)
    ja = (P.s < MAY).to_numpy()
    P0, _ = load(0) if seed else (P, None)
    flt = filters(P0, (P0.s < MAY).to_numpy())       # thresholds from the real Jan-Apr pool
    res, defs = [], []
    out = np.zeros((len(EXITS), len(COLS)))
    t = time.time()
    order_ent = ent  # fake outcomes: entry times differ from row order -> sort per definition
    for oi_f, oi_v in OICONDS:
        x = P[oi_f].to_numpy(float)
        m_oi = x >= oi_v if oi_f == "d5up" and False else (x <= -oi_v if oi_f == "d5up" else x <= oi_v)
        if oi_f == "d5up":
            m_oi = P.d5.to_numpy(float) >= oi_v
        for mv_f, mv_v in MOVES:
            mv = P[mv_f].to_numpy(float)
            m_mv = m_oi & (np.abs(mv) >= mv_v) & (mv != 0)
            for fade in (0, 1):
                d = np.sign(mv) * (-1 if fade else 1)
                for fi, (fname, fx, sg, th, side) in enumerate(flt):
                    if fx is None:
                        m = m_mv
                    else:
                        v = fx * d if sg else fx
                        m = m_mv & ((v >= th) if side == 1 else (v <= th))
                    rows = np.flatnonzero(m)
                    if len(rows) < 30:
                        continue
                    dsel = (d[rows] > 0).astype(np.int64)
                    e = order_ent[rows, dsel]
                    o = np.argsort(e, kind="stable")
                    rows, dsel = rows[o], dsel[o]
                    run_exits(rows, dsel, ent, px, sd, RT, XT, stop_of, A, MAY, APR, out)
                    keep = (out[:, 0] >= 20) & (out[:, 1] > 0)
                    if keep.any():
                        did = len(defs)
                        defs.append((oi_f, oi_v, mv_f, mv_v, fade, fname, th, side))
                        kk = np.flatnonzero(keep)
                        res.append(np.c_[np.full(len(kk), did), kk, out[kk]])
        print(oi_f, oi_v, len(defs), round(time.time() - t), flush=True)
    res = np.concatenate(res)
    df = pd.DataFrame(res, columns=["def", "exit"] + COLS)
    df["def"] = df["def"].astype(int)
    df["exit"] = df["exit"].astype(int)
    df.to_parquet(os.path.join(HERE, f"s1_{seed}{tag}.parquet"))
    pd.DataFrame(defs, columns=["oi_f", "oi_v", "mv_f", "mv_v", "fade", "flt", "th", "side"]).to_parquet(
        os.path.join(HERE, f"s1defs_{seed}{tag}.parquet"))
    print("done", len(df), time.time() - t)


if __name__ == "__main__":
    main(int(sys.argv[1]))
