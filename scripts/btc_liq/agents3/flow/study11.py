import numpy as np, pandas as pd, fast, events, btc_common as bc
L = fast.Lean(exness=False)
mid = np.load('/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/mid.npy').astype(np.float64)
m = L.metrics; oi = m.sum_open_interest.to_numpy(); mts = m.ts.to_numpy() - L.t0
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; okr = np.r_[False, np.diff(mts) == 300]
doi[~okr] = np.nan
lo = bc.ts_of('2026-01-01') - L.t0; hi = L.n - 8 * 3600 - 400
H = (300, 900, 1800, 3600, 7200, 14400, 28800)
for W, X in ((30, 6), (60, 6), (60, 8), (120, 8), (120, 12), (300, 8), (300, 12)):
    s, d = events.bursts(L.c, L.vol, W, X, 600, lo, hi)
    # bucket containing s-1
    ct = ((s - 1 + L.t0) // 300) * 300 - L.t0
    k = np.searchsorted(mts, ct); k = np.clip(k, 0, len(mts) - 1)
    has = mts[k] == ct
    dd = np.where(has, doi[k], np.nan)
    sk = ct + 360                         # decision when OI known
    v = L.vol[s]
    e0 = mid[sk + 2]
    out = {}
    for name, q in (('all', np.ones(len(s), bool)), ('oiDrop<-.25%', dd <= -0.0025), ('oi flat', np.abs(dd) < 0.001), ('oiUp>+.25%', dd >= 0.0025)):
        fw = [np.nanmean(d[q] * (mid[sk[q] + 2 + h] - e0[q]) / v[q]) for h in H]
        sd = [np.nanstd(d[q] * (mid[sk[q] + 2 + h] - e0[q]) / v[q]) / np.sqrt(q.sum()) for h in H]
        print(f'W{W} X{X} {name:12s} n{q.sum():5d}', ' '.join(f'{h}:{x:+.2f}({e:.2f})' for h, x, e in zip(H, fw, sd)))
