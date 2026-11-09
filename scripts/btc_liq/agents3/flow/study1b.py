import numpy as np, pandas as pd, fast, btc_common as bc
L = fast.Lean()
print(L.metrics[['create_time','ts','known_ts']].head(2))
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
# honest: row k describes [ts_k, ts_k+300); oi change doi[k] = oi[k]/oi[k-1]-1 describes that window; known ts_k+360
A = ts - L.t0; E = A + 300
good = ok & (A - 400 > 0) & (E + 1500 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(A), np.nan); mv[good] = L.c[E[good] - 1] / L.c[A[good] - 1] - 1
offs = np.arange(-300, 1501, 60)
def path(sel):
    P = []
    for k in np.flatnonzero(sel):
        e = E[k]; d = np.sign(mv[k]); v = L.vol[e + 60]
        P.append(d * (L.c[e + offs] - L.c[e + 60]) / v)
    return np.array(P)
for name, sel in [('oi<-0.5 mv>.3', good & (doi <= -0.005) & (np.abs(mv) >= 0.003)),
                  ('oi<-0.25 mv>.15', good & (doi <= -0.0025) & (np.abs(mv) >= 0.0015)),
                  ('oi>+0.3 mv>.3', good & (doi >= 0.003) & (np.abs(mv) >= 0.003)),
                  ('oi ~0 mv>.3', good & (np.abs(doi) < 0.001) & (np.abs(mv) >= 0.003))]:
    P = path(sel)
    print(name, len(P))
    print(' mean', ' '.join(f'{o}:{x:+.1f}' for o, x in zip(offs, np.nanmean(P, 0))))
    print(' med ', ' '.join(f'{o}:{x:+.1f}' for o, x in zip(offs, np.nanmedian(P, 0))))
