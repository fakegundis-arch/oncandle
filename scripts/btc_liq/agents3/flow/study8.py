import numpy as np, pandas as pd, fast, feats, btc_common as bc
L = fast.Lean()
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300] & np.r_[False, False, np.diff(ts[1:]) == 300]
T = ts - L.t0
good = ok & (T - 90000 > 0) & (T + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(T), np.nan); mv[good] = L.c[T[good]] / L.c[T[good] - 300] - 1
mvp = np.full(len(T), np.nan); mvp[good] = L.c[T[good] - 300] / L.c[T[good] - 600] - 1
dprev = np.r_[np.nan, doi[:-1]]
for pth in (0.0025, 0.004):
  for mth in (0.0015, 0.003):
    base = good & (np.abs(mv) >= mth)
    reg = base & (dprev <= -pth) & (np.sign(mv) == np.sign(mvp))
    for name, q in (('all', base), ('regime same-dir', reg)):
        print(pth, mth, name, q.sum(), 'P(doi<=-.25%)', round(np.mean(doi[q] <= -0.0025), 3), 'P(<=-.4%)', round(np.mean(doi[q] <= -0.004), 3))
# regime trades: enter at T (end of bucket) when prev bucket OI drop & current bucket move continues same dir
for pth in (0.0025, 0.004):
  for mth in (0.0015, 0.002, 0.003):
    q = np.flatnonzero(good & (dprev <= -pth) & (np.abs(mv) >= mth) & (np.sign(mv) == np.sign(mvp)))
    s = T[q]; d = np.sign(mv[q]).astype(int); vol = L.vol[s]
    for delay in (0, 60):
        tr = bc.trades(L, s + delay + L.t0, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)
        a = fast.acct(tr); conf = doi[q] <= -0.0025
        trc = tr[np.isin(tr.sig_ts, s[conf] + delay + L.t0)]
        print(pth, mth, delay, 'all', a['n'], round(a['R'], 1), round(a['pf'], 2), '| conf only', len(trc), round(trc.r.sum(), 1), '| unconf', round(tr.r.sum() - trc.r.sum(), 1))
