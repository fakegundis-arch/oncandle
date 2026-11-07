"""Walk-forward version of search.py: one pass over all data per combination, with cumulative snapshots at
2026-01-01, 2026-03-01, 2026-05-01 and 2026-07-01 so that 'select on data before X, trade the next 2 months' can be
replayed for every fold without look-ahead.  Usage: python search_wf.py [tag] [rand_dir_seed]"""
import os, sys, time
import numpy as np, pandas as pd
from numba import njit
from lib import WORK
import search as S

BOUNDS = [pd.Timestamp(x, tz="UTC").timestamp() for x in ["2026-01-01", "2026-03-01", "2026-05-01", "2026-07-01"]]
NB = len(BOUNDS)
COLS = ["n", "R", "gw", "gl", "w", "lg", "dd", "mp", "mt", "n2", "R2", "gw2", "gl2"]
NC = len(COLS)


@njit(cache=True)
def eval_wf(idx, dsel, dl, R, DT, ET, Rs, DTs, ETs, mon, nmon, bounds, bmon, out):
    """out[e, b, c]: cumulative stats of trades with entry < bounds[b]."""
    ns, nq, nh = R.shape[3], R.shape[4], R.shape[5]
    nb = bounds.shape[0]
    mr = np.zeros(nmon)
    e = 0
    for s in range(ns):
        for q in range(nq):
            for h in range(nh):
                last = -1
                n = 0; sr = 0.0; gw = 0.0; gl = 0.0; w = 0; lg = 0.0; peak = 0.0; dd = 0.0
                mr[:] = 0.0
                b = 0
                for k in range(idx.shape[0]):
                    i = idx[k]
                    et = ET[i, dl]
                    if et < 0 or et < last:
                        continue
                    r = R[i, dl, dsel[k], s, q, h]
                    if r != r:
                        continue
                    while b < nb and et >= bounds[b]:
                        out[e, b, 0] = n; out[e, b, 1] = sr; out[e, b, 2] = gw; out[e, b, 3] = gl; out[e, b, 4] = w
                        out[e, b, 5] = lg; out[e, b, 6] = dd
                        mp = 0; mt = 0
                        for m in range(bmon[b]):
                            if mr[m] != 0.0:
                                mt += 1
                                if mr[m] > 0:
                                    mp += 1
                        out[e, b, 7] = mp; out[e, b, 8] = mt
                        b += 1
                    last = et + DT[i, dl, dsel[k], s, q, h]
                    n += 1; sr += r
                    if r > 0:
                        gw += r; w += 1
                    else:
                        gl -= r
                    g = 1.0 + 0.1 * r
                    lg += np.log(g) if g > 1e-5 else -1e9
                    if lg > peak:
                        peak = lg
                    if lg - peak < dd:
                        dd = lg - peak
                    mr[mon[i]] += r
                while b < nb:
                    out[e, b, 0] = n; out[e, b, 1] = sr; out[e, b, 2] = gw; out[e, b, 3] = gl; out[e, b, 4] = w
                    out[e, b, 5] = lg; out[e, b, 6] = dd
                    mp = 0; mt = 0
                    for m in range(bmon[b]):
                        if mr[m] != 0.0:
                            mt += 1
                            if mr[m] > 0:
                                mp += 1
                    out[e, b, 7] = mp; out[e, b, 8] = mt
                    b += 1
                # stress chain
                last = -1
                n2 = 0; sr2 = 0.0; gw2 = 0.0; gl2 = 0.0
                b = 0
                for k in range(idx.shape[0]):
                    i = idx[k]
                    et = ETs[i, dl]
                    if et < 0 or et < last:
                        continue
                    r = Rs[i, dl, dsel[k], s, q, h]
                    if r != r:
                        continue
                    while b < nb and et >= bounds[b]:
                        out[e, b, 9] = n2; out[e, b, 10] = sr2; out[e, b, 11] = gw2; out[e, b, 12] = gl2
                        b += 1
                    last = et + DTs[i, dl, dsel[k], s, q, h]
                    n2 += 1; sr2 += r
                    if r > 0:
                        gw2 += r
                    else:
                        gl2 -= r
                while b < nb:
                    out[e, b, 9] = n2; out[e, b, 10] = sr2; out[e, b, 11] = gw2; out[e, b, 12] = gl2
                    b += 1
                e += 1


def keep_rows(out):
    """keep a combination if it qualifies for selection in at least one fold (train = snapshot 0, 1 or 2)."""
    ok = np.zeros(out.shape[0], bool)
    for b in range(3):
        n, R, gw, gl, R2 = out[:, b, 0], out[:, b, 1], out[:, b, 2], out[:, b, 3], out[:, b, 10]
        pf = np.where(gl > 0, gw / np.maximum(gl, 1e-9), 99)
        ok |= (n >= 30) & (pf > 1.1) & (R2 > 0)
    return ok


def run(tag="", rseed=-1):
    t0 = time.time()
    F, base, outc, ext = S.load(tag)
    ts = F.ts.to_numpy()
    valid_t = ts >= S.S0
    dt = pd.to_datetime(ts, unit="s")
    mon = ((dt.year - 2025) * 12 + dt.month - 1).to_numpy().astype(np.int64)
    nmon = 18
    bounds = np.array(BOUNDS, np.float64)
    bmon = np.array([12, 14, 16, 18], np.int64)
    flt = S.filters(F); fnames = list(flt)
    rng = np.random.default_rng(rseed) if rseed >= 0 else None
    blocks, meta = [], []; ncomb = 0
    rn_ref = None
    for ii, inst in enumerate(["gold", "nasdaq"]):
        oc = outc[inst]
        R, DT, ET, Rs, DTs, ETs = oc["R"], oc["DT"], oc["ET"], oc["R_s"], oc["DT_s"], oc["ET_s"]
        nex = R.shape[3] * R.shape[4] * R.shape[5]
        for di, dl in enumerate(oc["delays"]):
            rules = S.dir_rules(base, inst, int(dl), ext)
            rnames = list(rules); rn_ref = rnames
            valid = valid_t & (ET[:, di] >= 0)
            for ri, rn in enumerate(rnames):
                d = rules[rn]
                if rng is not None:
                    d = (d != 0).astype(np.int8) * rng.choice(np.array([-1, 1], np.int8), len(d))
                bm = valid & (d != 0)
                for fi, fn in enumerate(fnames):
                    idx = np.flatnonzero(bm & flt[fn])
                    if len(idx) < 30:
                        continue
                    out = np.zeros((nex, NB, NC), np.float32)
                    eval_wf(idx, (d[idx] < 0).astype(np.int64), di, R, DT, ET, Rs, DTs, ETs, mon, nmon, bounds, bmon, out)
                    ncomb += nex
                    kp = keep_rows(out)
                    if kp.any():
                        ex = np.flatnonzero(kp)
                        blocks.append(out[kp]); meta.append(np.column_stack([np.full(len(ex), ii), np.full(len(ex), di), np.full(len(ex), ri), np.full(len(ex), fi), ex]).astype(np.int32))
            print(inst, dl, "rows", sum(len(b) for b in blocks), round(time.time() - t0), flush=True)
    res = np.concatenate(blocks); mt = np.concatenate(meta)
    name = f"wf{tag}{'_rd%d' % rseed if rseed >= 0 else ''}"
    np.savez(f"{WORK}/{name}.npz", res=res, meta=mt, fnames=np.array(fnames), rnames=np.array(rn_ref), ncomb=ncomb)
    print("saved", name, len(res), "of", ncomb, round(time.time() - t0), flush=True)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "", int(sys.argv[2]) if len(sys.argv) > 2 else -1)
