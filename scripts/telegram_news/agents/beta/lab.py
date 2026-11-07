"""beta's research helpers: numba copies of common.py fills/exits/account (validated against common.py)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np, pandas as pd, numba as nb
import common as C

D = '/home/user/news_lab_data'


class Inst:
    """arrays of one instrument + derived series."""
    def __init__(self, inst, data_dir=D):
        tk = C.load_ticks(inst, data_dir)
        self.name = inst
        self.tk = tk
        self.t = tk['t']
        self.bf, self.bl, self.bmin, self.bmax = tk['bid_first'], tk['bid_last'], tk['bid_min'], tk['bid_max']
        self.af, self.al, self.amin, self.amax = tk['ask_first'], tk['ask_last'], tk['ask_min'], tk['ask_max']
        self.n = tk['n'].astype(np.float64)
        self.gaps = np.flatnonzero(np.diff(self.t) >= C.GAP).astype(np.int64)
        mid = (self.bl + self.al) / 2
        self.mid = mid
        dm = np.r_[0.0, np.diff(mid)]
        # do not count the jump across a pause
        dm[1:][np.diff(self.t) >= C.GAP] = 0.0
        self.cs2 = np.cumsum(dm * dm)
        self.csa = np.cumsum(np.abs(dm))
        self.csn = np.cumsum(self.n)
        self.css = np.cumsum(self.al - self.bl)

    def idx_before(self, ts):
        """index of the last bar with t < ts"""
        return np.searchsorted(self.t, ts) - 1

    def bar_at(self, ts):
        """vectorised common.bar_at: -1 where None"""
        i = np.searchsorted(self.t, ts)
        ok = i < len(self.t)
        i2 = np.minimum(i, len(self.t) - 1)
        ok &= (self.t[i2] - ts) <= 10
        return np.where(ok, i2, -1)

    def next_close(self, i):
        g = self.gaps
        k = np.searchsorted(g, i)
        return np.where(k < len(g), g[np.minimum(k, len(g) - 1)], len(self.t) - 1)


# ------------------------------------------------------------------ exit kernel (multi tp / hold in one pass)
@nb.njit(cache=True)
def exit_multi(t, bf, bmin, bmax, bl, af, amin, amax, al, gaps, j, fill, d, stop_dist, be, trail, tps, holds,
               stress, out_r, out_x):
    """one position filled in second j.  be/trail < 0 means None.  tps: target levels in R (np.inf = none).
    holds: max hold seconds (<=0 means none, exit at next close).  Fills out_r[q, h], out_x[q, h] (exit index).
    Same results as common.exit_trade for each (tp, hold)."""
    N = len(t)
    sp0 = af[j] - bf[j]
    sd = stop_dist
    if 3 * sp0 > sd:
        sd = 3 * sp0
    # next close
    lo_, hi_ = 0, len(gaps)
    while lo_ < hi_:
        m = (lo_ + hi_) // 2
        if gaps[m] < j:
            lo_ = m + 1
        else:
            hi_ = m
    end = gaps[lo_] if lo_ < len(gaps) else N - 1
    nh = len(holds)
    kend = np.empty(nh, np.int64)
    kmax = j + 1
    for h in range(nh):
        if holds[h] <= 0:
            kend[h] = end + 1
        else:
            target = t[j] + holds[h]
            # searchsorted left on t for target, starting from j
            lo_, hi_ = j, N
            while lo_ < hi_:
                m = (lo_ + hi_) // 2
                if t[m] < target:
                    lo_ = m + 1
                else:
                    hi_ = m
            kend[h] = min(lo_, end + 1)
        if kend[h] > kmax:
            kmax = kend[h]
    nq = len(tps)
    xq = np.full(nq, -1, np.int64)
    pq = np.zeros(nq)
    gq = np.zeros(nq, np.bool_)
    sl = fill - d * sd
    best = fill
    armed = be < 0
    use_path = (be >= 0) or (trail >= 0)
    xs = -1
    ps = 0.0
    qp = 0  # next tp level not yet hit (tps sorted ascending)
    for x in range(j + 1, kmax):
        if d > 0:
            f = bf[x]; adv = bmin[x]; fav = bmax[x]
        else:
            f = af[x]; adv = amax[x]; fav = amin[x]
        # tp first hits (levels independent of stop path)
        while qp < nq:
            tpp = fill + d * tps[qp] * sd
            if d * (f - tpp) >= 0:
                xq[qp] = x; pq[qp] = f; gq[qp] = True; qp += 1
            elif d * (fav - tpp) >= 0:
                xq[qp] = x; pq[qp] = tpp; gq[qp] = False; qp += 1
            else:
                break
        if d * (f - sl) <= 0:
            xs = x; ps = f; break
        if d * (adv - sl) <= 0:
            xs = x; ps = sl; break
        if use_path:
            if d > 0:
                if fav > best:
                    best = fav
            else:
                if fav < best:
                    best = fav
            if (not armed) and d * (best - fill) >= be * sd:
                armed = True
                if d * (fill - sl) > 0:
                    sl = fill
            if armed and trail >= 0:
                cand = best - d * trail * sd
                if d * (cand - sl) > 0:
                    sl = cand
    for q in range(nq):
        for h in range(nh):
            ke = kend[h]
            # candidate exit from tp / stop before ke
            ex = -1; px = 0.0
            tq = xq[q]
            if tq >= 0 and tq < ke and (xs < 0 or tq < xs or (tq == xs and gq[q])):
                ex = tq; px = pq[q]
            elif xs >= 0 and xs < ke:
                ex = xs; px = ps
            if ex < 0:
                if ke <= end and holds[h] > 0:
                    ex = ke
                    px = bf[ke] if d > 0 else af[ke]
                else:
                    ex = min(end, N - 1)
                    px = bl[ex] if d > 0 else al[ex]
            r = d * (px - fill) / sd
            if stress:
                kk = min(ex, N - 1)
                r -= (af[kk] - bf[kk]) / sd
            out_r[q, h] = r
            out_x[q, h] = ex
    return sd


@nb.njit(cache=True)
def pending_scan(t, bf, bmin, bmax, af, amin, amax, gaps, i0, buy_px, sell_px, kind, expire_s, stress):
    """common.pending_entry for one or two orders. kind 0 = stop, 1 = limit.  buy_px/sell_px = nan for no order.
    -> (j, d, fill) of the WORSE leg if both trigger in the same second; j=-1 if none."""
    N = len(t)
    lo_, hi_ = 0, len(gaps)
    while lo_ < hi_:
        m = (lo_ + hi_) // 2
        if gaps[m] < i0:
            lo_ = m + 1
        else:
            hi_ = m
    end = gaps[lo_] if lo_ < len(gaps) else N - 1
    target = t[i0] + expire_s
    lo_, hi_ = i0, N
    while lo_ < hi_:
        m = (lo_ + hi_) // 2
        if t[m] < target:
            lo_ = m + 1
        else:
            hi_ = m
    w = min(lo_, end + 1)
    k = 2.0 if stress else 1.0
    for x in range(i0 + 1, w):
        hb = False; hs = False
        if not np.isnan(buy_px):
            if kind == 0:
                hb = amax[x] >= buy_px
            else:
                hb = amin[x] <= buy_px - k * (af[x] - bf[x])
        if not np.isnan(sell_px):
            if kind == 0:
                hs = bmin[x] <= sell_px
            else:
                hs = bmax[x] >= sell_px + k * (af[x] - bf[x])
        if hb or hs:
            sp = af[x] - bf[x]
            if kind == 0:
                fb = max(buy_px, af[x]) + k * sp
                fs = min(sell_px, bf[x]) - k * sp
            else:
                fb = buy_px; fs = sell_px
            if hb and hs:
                return x, 0, 0.0   # both legs: caller handles (worse leg)
            if hb:
                return x, 1, fb
            return x, -1, fs
    return -1, 0, 0.0


# ------------------------------------------------------------------ account (same as common.account)
@nb.njit(cache=True)
def account_nb(entry_ts, exit_ts, r, risk, start, max_open):
    """trades must be sorted by (entry_ts, exit_ts).  -> final, dd, taken, skipped, log-growth-ish"""
    n = len(r)
    if n == 0:
        return start, 0.0, 0, 0
    keys = np.empty(2 * n, np.int64)
    for i in range(n):
        keys[i] = (exit_ts[i] * 2 + 0) * (2 * n) + i
        keys[n + i] = (entry_ts[i] * 2 + 1) * (2 * n) + i
    keys.sort()
    bal = start; peak = start; dd = 0.0
    stake = np.zeros(n)
    isopen = np.zeros(n, np.bool_)
    open_sum = 0.0
    taken = 0; skipped = 0
    wiped = False
    for e in range(2 * n):
        kk = keys[e]
        i = kk % (2 * n)
        kind = (kk // (2 * n)) % 2
        if kind == 0:
            if isopen[i]:
                isopen[i] = False
                open_sum -= stake[i]
                bal += stake[i] * r[i]
                if bal <= 0.01:
                    bal = 0.0; wiped = True
                if bal > peak:
                    peak = bal
                if peak > 0:
                    v = bal / peak - 1
                    if v < dd:
                        dd = v
        else:
            if wiped:
                skipped += 1
                continue
            st = risk * bal
            if open_sum + st > max_open * bal + 1e-9:
                skipped += 1
                continue
            stake[i] = st
            isopen[i] = True
            open_sum += st
            taken += 1
    return bal, dd, taken, skipped


def account_df(tr, risk=0.10):
    tr = tr.sort_values(['entry_ts', 'exit_ts'])
    return account_nb(tr.entry_ts.to_numpy(np.int64), tr.exit_ts.to_numpy(np.int64), tr.r.to_numpy(float),
                      risk, 1000.0, 0.30)


def args(I):
    return (I.t, I.bf, I.bmin, I.bmax, I.bl, I.af, I.amin, I.amax, I.al, I.gaps)


def pargs(I):
    return (I.t, I.bf, I.bmin, I.bmax, I.af, I.amin, I.amax, I.gaps)


@nb.njit(cache=True, parallel=True)
def market_batch(t, bf, bmin, bmax, bl, af, amin, amax, al, gaps, iD, d, sdist, be, trail, tps, holds, stress):
    """market entries at bar iD (common.market_entry fill), direction d, stop distance sdist.
    -> R[E, nq, nh], X[E, nq, nh] (exit bar), SD[E]"""
    E = len(iD)
    nq = len(tps); nh = len(holds)
    R = np.full((E, nq, nh), np.nan, np.float32)
    X = np.full((E, nq, nh), -1, np.int64)
    SD = np.full(E, np.nan)
    k = 2.0 if stress else 1.0
    for e in nb.prange(E):
        i = iD[e]
        if i < 0 or d[e] == 0 or not (sdist[e] > 0):
            continue
        sp = af[i] - bf[i]
        fill = (af[i] + k * sp) if d[e] > 0 else (bf[i] - k * sp)
        o_r = np.zeros((nq, nh)); o_x = np.zeros((nq, nh), np.int64)
        SD[e] = exit_multi(t, bf, bmin, bmax, bl, af, amin, amax, al, gaps, i, fill, d[e], sdist[e], be, trail,
                           tps, holds, stress, o_r, o_x)
        for q in range(nq):
            for h in range(nh):
                R[e, q, h] = o_r[q, h]; X[e, q, h] = o_x[q, h]
    return R, X, SD
