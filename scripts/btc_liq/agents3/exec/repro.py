import resource
import time

import numpy as np
import pandas as pd

import lab
from lab import bc

t = time.time()
L = lab.Lab()
print("load", time.time() - t, "rss GB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)
m = L.metrics
ts = m.ts.to_numpy()
oi = m.sum_open_interest.to_numpy()
prev_ok = np.r_[False, np.diff(ts) == 300]
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
doi[~prev_ok] = np.nan
i = ts - L.t0


def px(k):
    return L.c[np.clip(k, 0, L.n - 1)]


for variant in ("A", "B"):
    if variant == "A":   # last trade before T vs last trade before T-300
        mv = px(i - 1) / px(i - 301) - 1
    else:                # close of second T vs close of second T-300
        mv = px(i) / px(i - 300) - 1
    CB = np.r_[0.0, np.cumsum(L.bq, dtype=np.float64)]
    CS = np.r_[0.0, np.cumsum(L.sq, dtype=np.float64)]
    ii = np.clip(i, 300, L.n)
    net = (CB[ii] - CB[ii - 300]) - (CS[ii] - CS[ii - 300])
    dec = m.known_ts.to_numpy()
    vol = L.vol_at(dec)
    for name, th, extra, stop_k, tp, trail, be in (("v1", 0.007, False, 5, 2.0, np.nan, np.nan),
                                                   ("v2", 0.005, True, 8, 1.5, 1.0, 1.0)):
        sel = (doi <= -th) & (np.abs(mv) >= 0.003) & (dec >= bc.ts_of("2026-01-01")) & (dec < bc.ts_of("2026-07-01"))
        d = np.sign(mv)
        if extra:
            sel &= np.sign(net) == d
        s, dd, v = dec[sel], d[sel].astype(int), vol[sel]
        tr = bc.trades(L, s, dd, stop_dist=stop_k * v, tp_r=tp, hold=300, be_at=be, trail=trail)
        a = bc.account(tr, "2026-01-01", "2026-07-01", maxpos=1)
        print(variant, name, len(s), a)
