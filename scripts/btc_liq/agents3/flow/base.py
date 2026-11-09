import numpy as np, pandas as pd, fast, btc_common as bc

def oi_signals(L, oi_th, mv_th, flow=False, ver=0):
    m = L.metrics
    oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
    prev_ok = np.r_[False, np.diff(ts) == 300]
    doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
    T = ts - L.t0
    ok = prev_ok & (T - 301 >= 0) & (T + 60 < L.n)
    sig, dirs = [], []
    CB = np.r_[0, np.cumsum(L.raw['bq'], dtype=np.float64)]; CS = np.r_[0, np.cumsum(L.raw['sq'], dtype=np.float64)]
    for k in np.flatnonzero(ok & (doi <= -oi_th)):
        t = T[k]
        if ver == 0: mvv = L.c[t - 1] / L.c[t - 301] - 1
        else: mvv = L.c[t] / L.c[t - 300] - 1
        if abs(mvv) < mv_th: continue
        d = 1 if mvv > 0 else -1
        if flow:
            nf = (CB[t] - CB[t - 300]) - (CS[t] - CS[t - 300])
            if np.sign(nf) != d: continue
        sig.append(ts[k] + 60); dirs.append(d)
    return np.array(sig, np.int64), np.array(dirs, np.int64)
