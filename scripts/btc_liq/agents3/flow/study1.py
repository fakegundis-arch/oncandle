import numpy as np, pandas as pd, fast, base, btc_common as bc
L = fast.Lean()
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
T = ts - L.t0
good = ok & (T - 400 > 0) & (T + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(T), np.nan); mv[good] = L.c[T[good]] / L.c[T[good] - 300] - 1
offs = np.arange(-300, 1201, 30)
def path(sel):
    P = []
    for k in np.flatnonzero(sel):
        t = T[k]; d = np.sign(mv[k]); v = L.vol[t + 60]
        P.append(d * (L.c[t + offs] - L.c[t + 60]) / v)
    P = np.array(P); return P
for name, sel in [('oi<-0.5 mv>.3', good & (doi <= -0.005) & (np.abs(mv) >= 0.003)),
                  ('oi<-0.3 mv>.3', good & (doi <= -0.003) & (doi > -0.005) & (np.abs(mv) >= 0.003)),
                  ('oi>+0.3 mv>.3', good & (doi >= 0.003) & (np.abs(mv) >= 0.003)),
                  ('oi ~0 mv>.3', good & (np.abs(doi) < 0.001) & (np.abs(mv) >= 0.003))]:
    P = path(sel)
    print(name, len(P))
    print(' '.join(f'{o}:{x:+.1f}' for o, x in zip(offs, np.nanmean(P, 0)) if o % 60 == 0))
    print(' med', ' '.join(f'{o}:{x:+.1f}' for o, x in zip(offs, np.nanmedian(P, 0)) if o % 60 == 0))
