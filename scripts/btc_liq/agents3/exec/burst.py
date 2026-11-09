"""real-time burst triggers (Binance seconds < s) with / without a recently KNOWN open-interest-drop bucket.
forward Exness mid move (direction, vol units) from s+2 to s+2+H minus 2 spreads."""
import numba as nb
import numpy as np
import pandas as pd

import lab
from lab import bc

L = lab.Lab()
JAN, JUL = bc.ts_of("2026-01-01"), bc.ts_of("2026-06-30")
n = L.n
vol = L.vol_at(L.t0 + np.arange(n)).astype(np.float32)
CB = np.r_[0.0, np.cumsum(L.bq, dtype=np.float64)]
CS = np.r_[0.0, np.cumsum(L.sq, dtype=np.float64)]


@nb.njit(cache=True)
def scan(c, vol, CB, CS, W, X, start, stop, gap):
    out = []
    last = -10 ** 9
    for s in range(start, stop):
        if s - last < gap:
            continue
        v = vol[s]
        if not (v > 0):
            continue
        mvv = (c[s - 1] - c[s - 1 - W]) / v
        if abs(mvv) < X:
            continue
        d = 1 if mvv > 0 else -1
        net = (CB[s] - CB[s - W]) - (CS[s] - CS[s - W])
        if net * d <= 0:
            continue
        out.append(s)
        last = s
    return np.array(out, np.int64)


T_ = L.tk["t"]
mid = 0.5 * (L.tk["bid_last"] + L.tk["ask_last"])


def ex(t):
    k = np.searchsorted(T_, t, side="right") - 1
    return mid[np.clip(k, 0, len(mid) - 1)]


m = L.metrics
mts = m.ts.to_numpy()
oi = m.sum_open_interest.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
doi[~np.r_[False, np.diff(mts) == 300]] = np.nan
bend = mts + 300 - L.t0
bmv = L.c[np.clip(bend, 0, n - 1)] / L.c[np.clip(bend - 300, 0, n - 1)] - 1
known = m.known_ts.to_numpy()
rows = []
for W in (30, 60, 120):
    for X in (3, 5, 8):
        s = scan(L.c, vol, CB, CS, W, X, JAN - L.t0, JUL - L.t0, 300)
        ts = s + L.t0
        d = np.sign(L.c[s - 1] - L.c[s - 1 - W])
        q = np.searchsorted(T_, ts) - 1
        sp = (L.tk["ask_last"] - L.tk["bid_last"])[q]
        cost = 2 * sp / vol[s]
        # recent known OI rows: within last 15 min of known time
        k = np.searchsorted(known, ts, side="right") - 1
        ctx = np.zeros(len(s), np.int64)  # 1 = OI-drop bucket (<= -0.3%) with same-dir move known within 15 min
        for j in range(len(s)):
            kk = k[j]
            while kk >= 0 and ts[j] - known[kk] <= 900:
                if doi[kk] <= -0.003 and np.sign(bmv[kk]) == d[j] and abs(bmv[kk]) >= 0.002:
                    ctx[j] = 1
                    break
                kk -= 1
        mo = pd.to_datetime(ts, unit="s").month
        for H in (60, 120, 300, 600):
            y = d * (ex(ts + 2 + H) - ex(ts + 2)) / vol[s] - cost
            for c_ in (0, 1):
                sel = ctx == c_
                if sel.sum() < 10:
                    continue
                pm = pd.Series(y[sel]).groupby(mo[sel]).mean()
                rows.append(dict(W=W, X=X, H=H, ctx=c_, n=sel.sum(), mean=y[sel].mean(),
                                 gross=(y + cost)[sel].mean(), t=y[sel].mean() / y[sel].std() * np.sqrt(sel.sum()),
                                 pos_m=(pm > 0).sum()))
R = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(R.round(2).to_string())
