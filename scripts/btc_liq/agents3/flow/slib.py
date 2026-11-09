"""fast account evaluation for the search (same logic as btc_common.nb_account, plus a mask and sub-period R)."""
import numpy as np, numba as nb


@nb.njit(cache=True)
def acct_mask(ent, ext, rr, sds, pxs, mask, maxpos, start_ts, mid_ts, end_ts):
    """events sorted by entry.  -> n, R, gross win, gross loss, final, maxdd, R before mid_ts, R after"""
    risk, cap, maxopen = 0.10, 100.0, 0.30
    bal, peak, dd = 1000.0, 1000.0, 0.0
    o_on = np.zeros(16, np.bool_); o_exit = np.zeros(16, np.int64); o_lot = np.zeros(16); o_sd = np.zeros(16); o_r = np.zeros(16)
    n = 0; R = gw = gl = Ra = Rb = 0.0
    m = len(rr)
    for e in range(m + 1):
        last = e == m
        if not last and (not mask[e] or np.isnan(rr[e]) or ent[e] < start_ts or ent[e] >= end_ts):
            continue
        while True:
            best, bk = -1, 0
            for s in range(16):
                if o_on[s] and (last or o_exit[s] <= ent[e]) and (best < 0 or o_exit[s] < best):
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
                cnt += 1; ro += o_lot[s] * o_sd[s]
        if cnt >= maxpos or bal <= 0:
            continue
        st = risk * bal
        if ro + st > maxopen * bal + 1e-9:
            continue
        lot = min(st / sds[e], cap * bal / pxs[e])
        for s in range(16):
            if not o_on[s]:
                o_on[s], o_exit[s], o_lot[s], o_sd[s], o_r[s] = True, ext[e], lot, sds[e], rr[e]
                break
        n += 1; R += rr[e]
        if ent[e] < mid_ts:
            Ra += rr[e]
        else:
            Rb += rr[e]
        if rr[e] > 0:
            gw += rr[e]
        else:
            gl -= rr[e]
    return n, R, gw, gl, bal, dd, Ra, Rb


import btc_common as bc


def outcomes(L, sig, dirs, grid, stress=False):
    """sig (unix s, sorted), dirs -> arrays [len(grid), n] of ent, ext, r, sd, px.  grid rows: stop_k, tp, hold, be, trail
    (stop in units of vol at the decision second)."""
    tk = L.tk
    sig = np.asarray(sig, np.int64); dirs = np.asarray(dirs, np.int64); n = len(sig)
    vol = L.vol[sig - L.t0]
    G = len(grid)
    E = np.zeros((G, n), np.int64); X = np.zeros((G, n), np.int64); R = np.full((G, n), np.nan); S = np.zeros((G, n)); P = np.zeros((G, n))
    for g, (k, tp, hold, be, tr) in enumerate(grid):
        f = lambda v, t: np.full(n, v, t)
        e, x, r, sd, px = bc.nb_trades(tk['t'], tk['bid_first'], tk['bid_last'], tk['bid_min'], tk['bid_max'],
                                       tk['ask_first'], tk['ask_last'], tk['ask_min'], tk['ask_max'], L.gaps, sig, dirs,
                                       f(0, np.int64), f(0.0, float), f(180, np.int64), k * vol, f(tp, float), f(hold, np.int64),
                                       f(be, float), f(tr, float), stress)
        E[g], X[g], R[g], S[g], P[g] = e, x, r, sd, px
    return E, X, R, S, P
