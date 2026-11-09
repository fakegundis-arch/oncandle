import numpy as np, pandas as pd, fast, feats, btc_common as bc, time
L = fast.Lean(); P = feats.Pre(L)
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
T = ts - L.t0
good = ok & (T - 90000 > 0) & (T + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(T), np.nan); mv[good] = L.c[T[good]] / L.c[T[good] - 300] - 1
sel = np.flatnonzero(good & (np.abs(mv) >= 0.003))
s = T[sel]; d = np.sign(mv[sel]).astype(np.int64)
t = time.time(); F = feats.compute(P, s, d); print('feat', time.time() - t, len(F))
F['doi'] = doi[sel]; F['mv'] = mv[sel]
# forward outcomes: entry at T (decision s=T), V2 exit
vol = L.vol[s]
for name, sig in (('atT', s + L.t0), ('atT60', s + 60 + L.t0)):
    tr = bc.trades(L, sig, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)
    F[name] = pd.Series(tr.r.to_numpy(), index=np.searchsorted(sig, tr.sig_ts))
F['fwd300'] = d * (L.c[s + 300] - L.c[s]) / vol
F.to_pickle('cache_bucket_feats.pkl')
y = (F.doi <= -0.005).astype(int)
from scipy.stats import spearmanr
rows = []
for col in F.columns:
    if col in ('doi', 'atT', 'atT60', 'fwd300'): continue
    x = F[col]
    okk = x.notna() & np.isfinite(x)
    if okk.sum() < 100: continue
    from sklearn.metrics import roc_auc_score
    try: auc = roc_auc_score(y[okk], x[okk])
    except Exception: auc = np.nan
    rows.append((col, auc, spearmanr(x[okk], F.doi[okk])[0], spearmanr(x[okk], F.atT[okk].fillna(0))[0], spearmanr(x[okk], F.fwd300[okk])[0]))
R = pd.DataFrame(rows, columns=['f', 'auc_oidrop', 'rho_doi', 'rho_rT', 'rho_fwd']).sort_values('auc_oidrop')
pd.set_option('display.width', 200); print(R.to_string())
print(F.groupby(y)[['atT', 'atT60', 'fwd300']].agg(['mean', 'count']))
