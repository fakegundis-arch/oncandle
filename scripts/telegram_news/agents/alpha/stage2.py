"""Stage 2: exit refinement (stop, target, timer, break-even, trailing) for given signals, numba port of common.py."""
import numpy as np, pandas as pd
from numba import njit, prange
from lib import C
from engine import gaps, next_close_v, bar_at_v, sim_trail_one


@njit(parallel=True, cache=True)
def batch_trail(js, ds, sds, ends, kends, timers_on, tp_r, be, tr, bf, bmin, bmax, blast, af, amax, amin, alast, k_entry):
    n = js.shape[0]
    R = np.full(n, np.nan); X = np.full(n, -1, np.int64); SD = np.full(n, np.nan)
    for e in prange(n):
        j = js[e]
        if j < 0:
            continue
        d = ds[e]
        sp = af[j] - bf[j]
        fill = (af[j] if d > 0 else bf[j]) + d * k_entry * sp
        sd = max(sds[e], 3 * sp)
        x, px = sim_trail_one(j, fill, d, sd, ends[e], kends[e], timers_on[e], tp_r, be, tr, bf, bmin, bmax, blast, af, amax, amin, alast)
        R[e] = d * (px - fill) / sd; X[e] = x; SD[e] = sd
    return R, X, SD


def outcomes(tk, g, dec_ts, ds, sds, tp_r=None, max_hold=None, be=None, trail=None, stress=False):
    T = tk["t"]
    js = bar_at_v(T, dec_ts)
    jj = np.clip(js, 0, len(T) - 1)
    ends = next_close_v(T, g, jj)
    if max_hold is None:
        kends = ends + 1
    else:
        kends = np.minimum(np.searchsorted(T, T[jj] + max_hold), ends + 1)
    timers_on = (max_hold is not None) & (kends <= ends)
    timers_on = np.broadcast_to(timers_on, js.shape).copy()
    R, X, SD = batch_trail(js.astype(np.int64), ds.astype(np.int64), np.nan_to_num(sds).astype(float), ends.astype(np.int64),
                           kends.astype(np.int64), timers_on, np.inf if tp_r is None else float(tp_r),
                           -1.0 if be is None else float(be), -1.0 if trail is None else float(trail),
                           tk["bid_first"], tk["bid_min"], tk["bid_max"], tk["bid_last"],
                           tk["ask_first"], tk["ask_max"], tk["ask_min"], tk["ask_last"], 2.0 if stress else 1.0)
    Xc = np.clip(X, 0, len(T) - 1)
    if stress:
        R = R - (tk["ask_first"][Xc] - tk["bid_first"][Xc]) / SD
    ET = np.where(js >= 0, T[jj], -1); XT = np.where(js >= 0, T[Xc], -1)
    return R, ET, XT, SD


def dedupe(ET, XT, R):
    """one position at a time (entries sorted by time)."""
    keep = np.zeros(len(ET), bool); last = -1
    for i in range(len(ET)):
        if ET[i] < 0 or not np.isfinite(R[i]) or ET[i] < last:
            continue
        keep[i] = True; last = XT[i]
    return keep
