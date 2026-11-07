"""alpha: numba copy of common.pending_entry (stop / limit / OCO) followed by fixed stop/target/timer exits.
If two legs trigger in the same second, both are simulated and the WORSE r is kept (per exit combo)."""
from __future__ import annotations
import numpy as np
from numba import njit, prange
from lib import C
from engine import _sim_one, gaps, next_close_v, bar_at_v


@njit(cache=True)
def _pending(i0, wend, kinds, dirs, pxs, bf, af, bmin, bmax, amin, amax, k, legd, legf):
    """first second in (i0, wend) where any order triggers -> j (or -1); legs written to legd/legf; returns (j, nlegs)."""
    a = i0 + 1
    if a >= wend:
        return -1, 0
    no = kinds.shape[0]
    for x in range(a, wend):
        nl = 0
        for o in range(no):
            d = dirs[o]; px = pxs[o]
            if kinds[o] == 0:
                h = (amax[x] >= px) if d > 0 else (bmin[x] <= px)
            else:
                sp = af[x] - bf[x]
                h = (amin[x] <= px - k * sp) if d > 0 else (bmax[x] >= px + k * sp)
            if h:
                if kinds[o] == 0:
                    fill = (max(px, af[x]) if d > 0 else min(px, bf[x])) + d * k * (af[x] - bf[x])
                else:
                    fill = px
                legd[nl] = d; legf[nl] = fill; nl += 1
        if nl > 0:
            return x, nl
    return -1, 0


@njit(parallel=True, cache=True)
def sim_oco_batch(i0s, wends, gidx, T, offs_up, offs_dn, kind_up, kind_dn, sds, timers, tps,
                  bf, bmin, bmax, blast, af, amax, amin, alast, k):
    """i0s: decision second index.  Two orders: (kind_up, +1, ref + offs_up) and (kind_dn, -1, ref - offs_dn) where
    ref = mid of the first quote of i0 (kind 0 stop / 1 limit; offs <= 0 disables).  sds: stop distance.
    -> R[n, nq, nh], X exit idx, J entry idx, D dir, SD."""
    n = i0s.shape[0]
    nq = tps.shape[0]; nh = timers.shape[0]
    R = np.full((n, nq, nh), np.nan, np.float32)
    X = np.full((n, nq, nh), -1, np.int64)
    J = np.full(n, -1, np.int64)
    D = np.zeros(n, np.int64)
    SD = np.full(n, np.nan)
    for e in prange(n):
        i0 = i0s[e]
        if i0 < 0:
            continue
        ref = 0.5 * (af[i0] + bf[i0])
        kinds = np.zeros(2, np.int64); dirs = np.zeros(2, np.int64); pxs = np.zeros(2)
        no = 0
        if offs_up[e] > 0:
            kinds[no] = kind_up; dirs[no] = 1; pxs[no] = ref + offs_up[e]; no += 1
        if offs_dn[e] > 0:
            kinds[no] = kind_dn; dirs[no] = -1; pxs[no] = ref - offs_dn[e]; no += 1
        if no == 0:
            continue
        legd = np.zeros(2, np.int64); legf = np.zeros(2)
        j, nl = _pending(i0, wends[e], kinds[:no], dirs[:no], pxs[:no], bf, af, bmin, bmax, amin, amax, k, legd, legf)
        if j < 0:
            continue
        # exit set-up for entry j
        gk = np.searchsorted(gidx, j)
        end = gidx[gk] if gk < gidx.shape[0] else T.shape[0] - 1
        kends = np.empty(nh, np.int64)
        for h in range(nh):
            kends[h] = min(np.searchsorted(T, T[j] + timers[h]), end + 1)
        sp = af[j] - bf[j]
        sd = max(sds[e], 3 * sp)
        best = np.full((nq, nh), 1e300); bx = np.zeros((nq, nh), np.int64)
        for L in range(nl):
            rr = np.zeros((nq, nh)); xx = np.zeros((nq, nh), np.int64)
            _sim_one(j, legf[L], legd[L], sd, end, kends, tps, bf, bmin, bmax, blast, af, amax, amin, alast, rr, xx)
            for q in range(nq):
                for h in range(nh):
                    if rr[q, h] < best[q, h]:
                        best[q, h] = rr[q, h]; bx[q, h] = xx[q, h]
        for q in range(nq):
            for h in range(nh):
                R[e, q, h] = best[q, h]; X[e, q, h] = bx[q, h]
        J[e] = j; D[e] = legd[0] if nl == 1 else 0; SD[e] = sd
    return R, X, J, D, SD


def oco_outcomes(tk, g, dec_ts, offs_up, offs_dn, sds, expire_s, tps, timers, kind_up=0, kind_dn=0, stress=False):
    T = tk["t"]
    i0 = bar_at_v(T, dec_ts)
    ii = np.clip(i0, 0, len(T) - 1)
    end0 = next_close_v(T, g, ii)
    wends = np.minimum(np.searchsorted(T, T[ii] + expire_s), end0 + 1)
    R, X, J, D, SD = sim_oco_batch(i0.astype(np.int64), wends.astype(np.int64), g.astype(np.int64), T,
                                   np.asarray(offs_up, float), np.asarray(offs_dn, float), kind_up, kind_dn,
                                   np.asarray(sds, float), np.asarray(timers, np.int64), np.asarray(tps, float),
                                   tk["bid_first"], tk["bid_min"], tk["bid_max"], tk["bid_last"],
                                   tk["ask_first"], tk["ask_max"], tk["ask_min"], tk["ask_last"], 2.0 if stress else 1.0)
    if stress:
        Xc = np.clip(X, 0, len(T) - 1)
        sp = tk["ask_first"][Xc] - tk["bid_first"][Xc]
        R = R - (sp / SD[:, None, None]).astype(np.float32)
    return i0, R, X, J, D, SD
