import numpy as np, pandas as pd, fast, feats, btc_common as bc
from sklearn.metrics import roc_auc_score
from scipy.stats import spearmanr
L = fast.Lean(); P = feats.Pre(L)
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
A = ts - L.t0; E = A + 300
good = ok & (A - 90000 > 0) & (E + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(A), np.nan); mv[good] = L.c[E[good] - 1] / L.c[A[good] - 1] - 1
sel = np.flatnonzero(good & (np.abs(mv) >= 0.003))
s = E[sel]; d = np.sign(mv[sel]).astype(np.int64)   # features at window end (decision at E uses seconds < E)
F = feats.compute(P, s, d)
F['doi'] = doi[sel]; F['ts'] = s + L.t0; F['d'] = d
vol = L.vol[s]
# forward outcomes follow from E and fade from E, and follow/fade from E+60 (OI known)
for name, delay, sgn in (('folE', 0, 1), ('fadE', 0, -1), ('fol60', 60, 1), ('fad60', 60, -1)):
    sig = s + delay + L.t0
    tr = bc.trades(L, sig, sgn * d, stop_dist=8 * vol, hold=600)
    F[name] = pd.Series(tr.r.to_numpy(), index=np.searchsorted(sig, tr.sig_ts))
F.to_pickle('cache_bucket_honest.pkl')
y = (F.doi <= -0.004).astype(int)
print('base rate', y.mean(), len(F))
rows = []
for col in F.columns:
    if col in ('doi', 'ts', 'd', 'folE', 'fadE', 'fol60', 'fad60', 'oi_age', 'bucket_pos'): continue
    x = F[col].astype(float); okk = x.notna() & np.isfinite(x)
    try: auc = roc_auc_score(y[okk], x[okk])
    except Exception: auc = np.nan
    rows.append((col, auc, spearmanr(x[okk], F.doi[okk])[0], spearmanr(x[okk], F.folE.fillna(0)[okk])[0], spearmanr(x[okk], F.fol60.fillna(0)[okk])[0]))
R = pd.DataFrame(rows, columns=['f', 'auc_oidrop', 'rho_doi', 'rho_folE', 'rho_fol60']).sort_values('auc_oidrop')
pd.set_option('display.width', 200); print(R.to_string())
print(F.groupby(y)[['folE', 'fadE', 'fol60', 'fad60']].mean())
