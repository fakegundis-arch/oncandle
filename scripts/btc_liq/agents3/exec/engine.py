"""fast evaluation helpers: per-signal outcomes for many settings, account over many masks."""
import numba as nb
import numpy as np
import pandas as pd

import lab
from lab import bc

JAN, MAY, JUL = bc.ts_of("2026-01-01"), bc.ts_of("2026-05-01"), bc.ts_of("2026-07-01")
APR = bc.ts_of("2026-04-01")


def outcomes(L, sig, dirs, kind, offset, life, stop_dist, tp_r, hold, be_at, trail, stress=False):
    ent, ext, rr, sds, pxs = L.nbt(sig, dirs, kind, offset, life, stop_dist, tp_r, hold, be_at, trail, stress)
    return ent, ext, rr, sds, pxs


@nb.njit(cache=True)
def acct_mask(ent, ext, rr, sds, pxs, mask, maxpos, start, end):
    """ent etc. sorted by entry; mask bool -> stats"""
    m = mask & ~np.isnan(rr)
    idx = np.flatnonzero(m)
    return bc.nb_account(ent[idx], ext[idx], rr[idx], sds[idx], pxs[idx], maxpos, 0.10, 100.0, 0.30, start, end)


@nb.njit(cache=True)
def acct_full(ent, ext, rr, sds, pxs, mask, maxpos, start, end):
    """like nb_account but also returns per-trade taken flag (for R split / month stats)"""
    m = mask & ~np.isnan(rr)
    idx = np.flatnonzero(m)
    e_, x_, r_, s_, p_ = ent[idx], ext[idx], rr[idx], sds[idx], pxs[idx]
    taken = np.zeros(len(rr), np.bool_)
    bal, peak, dd = 1000.0, 1000.0, 0.0
    o_on = np.zeros(16, np.bool_)
    o_exit = np.zeros(16, np.int64)
    o_lot = np.zeros(16)
    o_sd = np.zeros(16)
    o_r = np.zeros(16)
    bals = np.zeros(len(rr))
    for q in range(len(r_) + 1):
        last = q == len(r_)
        if not last and (e_[q] < start or e_[q] >= end):
            continue
        while True:
            best, bk = -1, 0
            for s in range(16):
                if o_on[s] and (last or o_exit[s] <= e_[q]) and (best < 0 or o_exit[s] < best):
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
        for s in range(16):
            if o_on[s]:
                cnt += 1
                ro += o_lot[s] * o_sd[s]
        if cnt >= maxpos or bal <= 0:
            continue
        st = 0.1 * bal
        if ro + st > 0.3 * bal + 1e-9:
            continue
        lot = min(st / s_[q], 100.0 * bal / p_[q])
        for s in range(16):
            if not o_on[s]:
                o_on[s], o_exit[s], o_lot[s], o_sd[s], o_r[s] = True, x_[q], lot, s_[q], r_[q]
                break
        taken[idx[q]] = True
    return taken, bal, dd


def stats(ent, ext, rr, sds, pxs, mask, maxpos, start, end):
    n, wn, R, gw, gl, bal, dd, ml = acct_mask(ent, ext, rr, sds, pxs, mask, maxpos, start, end)
    return dict(n=int(n), R=float(R), pf=float(gw / gl) if gl > 0 else 99.0, win=wn / max(n, 1), final=float(bal),
                dd=float(dd), max_lot=float(ml))
