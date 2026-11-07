"""alpha: fast numba copies of common.py market entry + fixed stop/target/timer exits (checked against common.py)."""
from __future__ import annotations

import numpy as np
from numba import njit, prange

from lib import C


def gaps(T):
    return np.flatnonzero(np.diff(T) >= C.GAP)


def next_close_v(T, g, j):
    k = np.searchsorted(g, j)
    return np.where(k < len(g), g[np.clip(k, 0, max(len(g) - 1, 0))], len(T) - 1)


def bar_at_v(T, x):
    i = np.searchsorted(T, x)
    ok = i < len(T)
    ii = np.clip(i, 0, len(T) - 1)
    ok &= (T[ii] - x) <= 10
    return np.where(ok, ii, -1)


@njit(cache=True)
def _sim_one(j, fill, d, sd, end, kends, tps, bf, bmin, bmax, blast, af, amax, amin, alast, rout, xout):
    """one market position, all (tp, timer) combos.  kends sorted ascending (same order as timers)."""
    nq = tps.shape[0]
    nh = kends.shape[0]
    sl = fill - d * sd
    if d > 0:
        first, adv, fav, last = bf, bmin, bmax, blast
    else:
        first, adv, fav, last = af, amax, amin, alast
    kmax = kends[nh - 1]
    ev_x = np.full(nq, -1, np.int64)
    ev_px = np.zeros(nq)
    nopen = nq
    x = j + 1
    while x < kmax and nopen > 0:
        f = first[x]
        a = adv[x]
        fv = fav[x]
        g_sl = d * (f - sl) <= 0
        h_sl = d * (a - sl) <= 0
        for q in range(nq):
            if ev_x[q] >= 0:
                continue
            tp = fill + d * tps[q] * sd
            g_tp = d * (f - tp) >= 0
            h_tp = d * (fv - tp) >= 0
            if g_sl or h_sl or g_tp or h_tp:
                ev_x[q] = x
                if g_sl or g_tp:
                    ev_px[q] = f
                elif h_sl:
                    ev_px[q] = sl
                else:
                    ev_px[q] = tp
                nopen -= 1
        x += 1
    for q in range(nq):
        for h in range(nh):
            ke = kends[h]
            if ev_x[q] >= 0 and ev_x[q] < ke:
                xx, px = ev_x[q], ev_px[q]
            elif ke <= end:
                xx, px = ke, first[ke]
            else:
                xx, px = end, last[end]
            rout[q, h] = d * (px - fill) / sd
            xout[q, h] = xx


@njit(parallel=True, cache=True)
def sim_market_batch(js, ds, sds, ends, kends, tps, bf, bmin, bmax, blast, af, amax, amin, alast, stress_k):
    """js: entry second index (-1 = no trade); ds: direction; sds: requested stop distance.
    Fill = market fill at js (common.market_entry), sd raised to 3 spreads.  -> r [n, nq, nh], exit idx, sd used."""
    n = js.shape[0]
    nq = tps.shape[0]
    nh = kends.shape[1]
    R = np.full((n, nq, nh), np.nan, np.float32)
    X = np.full((n, nq, nh), -1, np.int64)
    SD = np.full(n, np.nan)
    for e in prange(n):
        j = js[e]
        if j < 0:
            continue
        d = ds[e]
        sp = af[j] - bf[j]
        fill = (af[j] if d > 0 else bf[j]) + d * stress_k * sp
        sd = max(sds[e], 3 * sp)
        SD[e] = sd
        rr = np.zeros((nq, nh))
        xx = np.zeros((nq, nh), np.int64)
        _sim_one(j, fill, d, sd, ends[e], kends[e], tps, bf, bmin, bmax, blast, af, amax, amin, alast, rr, xx)
        for q in range(nq):
            for h in range(nh):
                R[e, q, h] = rr[q, h]
                X[e, q, h] = xx[q, h]
    return R, X, SD


def market_outcomes(tk, g, dec_ts, ds, sds, tps, timers, stress=False):
    """dec_ts: decision second (post + LAT + delay) per event.  Mirrors common.market_entry + exit_trade."""
    T = tk["t"]
    js = bar_at_v(T, dec_ts)
    jj = np.clip(js, 0, len(T) - 1)
    ends = next_close_v(T, g, jj)
    kends = np.empty((len(js), len(timers)), np.int64)
    for h, H in enumerate(timers):
        kends[:, h] = np.minimum(np.searchsorted(T, T[jj] + H), ends + 1)
    sds = np.where(np.isfinite(sds), sds, 0.0)
    R, X, SD = sim_market_batch(js.astype(np.int64), ds.astype(np.int64), sds.astype(np.float64), ends.astype(np.int64), kends, np.asarray(tps, float),
                                tk["bid_first"], tk["bid_min"], tk["bid_max"], tk["bid_last"],
                                tk["ask_first"], tk["ask_max"], tk["ask_min"], tk["ask_last"], 2.0 if stress else 1.0)
    if stress:
        Xc = np.clip(X, 0, len(T) - 1)
        sp = tk["ask_first"][Xc] - tk["bid_first"][Xc]
        R = R - (sp / SD[:, None, None]).astype(np.float32)
    return js, R, X, SD


@njit(cache=True)
def sim_trail_one(j, fill, d, sd, end, k_end, timer, tp_r, be_at_r, trail_r, bf, bmin, bmax, blast, af, amax, amin, alast):
    """port of common.exit_trade's break-even / trailing branch (be_at_r / trail_r < 0 mean None, tp_r inf = None)."""
    if d > 0:
        first, lo, hi, last = bf, bmin, bmax, blast
    else:
        first, lo, hi, last = af, amax, amin, alast
    sl = fill - d * sd
    has_tp = tp_r < 1e300
    tp = fill + d * tp_r * sd if has_tp else 0.0
    best = fill
    armed = be_at_r < 0
    for x in range(j + 1, k_end):
        f = first[x]; adv = lo[x]; fav = hi[x]
        if d * (f - sl) <= 0:
            return x, f
        if has_tp and d * (f - tp) >= 0:
            return x, f
        if d * (adv - sl) <= 0:
            return x, sl
        if has_tp and d * (fav - tp) >= 0:
            return x, tp
        best = max(best, fav) if d > 0 else min(best, fav)
        if not armed and d * (best - fill) >= be_at_r * sd:
            armed = True
            if d * (fill - sl) > 0:
                sl = fill
        if armed and trail_r >= 0:
            cand = best - d * trail_r * sd
            if d * (cand - sl) > 0:
                sl = cand
    if timer:
        return k_end, first[k_end]
    k = min(end, first.shape[0] - 1)
    return k, last[k]
