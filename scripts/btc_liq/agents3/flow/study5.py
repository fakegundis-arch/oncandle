import numpy as np, pandas as pd, fast, feats, btc_common as bc, time
from scipy.stats import spearmanr
L = fast.Lean(); P = feats.Pre(L)
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
T = ts - L.t0
good = ok & (T - 90000 > 0) & (T + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(T), np.nan); mv[good] = L.c[T[good]] / L.c[T[good] - 300] - 1
sel = np.flatnonzero(good & (doi <= -0.0025) & (np.abs(mv) >= 0.0015))
print('events', len(sel))
s = T[sel] + 60; d = np.sign(mv[sel]).astype(np.int64)
F = feats.compute(P, s, d)
F['doi'] = doi[sel]; F['mv'] = mv[sel] * d; F['ts'] = s + L.t0; F['d'] = d
F['doi_prev'] = doi[sel - 1]; F['mv_prev'] = d * (L.c[T[sel] - 300] / L.c[T[sel] - 600] - 1)
F['cnt_bucket_dv'] = None
vol = L.vol[s]
for name, kw in (('v2', dict(stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)),
                 ('h300', dict(stop_dist=8 * vol, hold=300)), ('h600', dict(stop_dist=10 * vol, hold=600)),
                 ('h120', dict(stop_dist=8 * vol, hold=120))):
    tr = bc.trades(L, s + L.t0, d, **kw)
    F[name] = pd.Series(tr.r.to_numpy(), index=np.searchsorted(s + L.t0, tr.sig_ts))
F.to_pickle('cache_oi_feats.pkl')
y = F.v2.fillna(0)
for th in (0.0025, 0.003, 0.004, 0.005, 0.007):
    for mth in (0.0015, 0.002, 0.003):
        q = (F.doi <= -th) & (F.mv >= mth)
        print(th, mth, q.sum(), 'v2 R', round(F.v2[q].sum(), 1), 'h300', round(F.h300[q].sum(), 1), 'h600', round(F.h600[q].sum(), 1), 'h120', round(F.h120[q].sum(), 1))
rows = []
for col in F.columns:
    if col in ('v2', 'h300', 'h600', 'h120', 'ts', 'd', 'cnt_bucket_dv'): continue
    x = F[col].astype(float); okk = x.notna() & np.isfinite(x)
    rows.append((col, spearmanr(x[okk], y[okk])[0], spearmanr(x[okk], F.h600.fillna(0)[okk])[0]))
R = pd.DataFrame(rows, columns=['f', 'rho_v2', 'rho_h600']).sort_values('rho_v2')
pd.set_option('display.width', 200); print(R.to_string())
