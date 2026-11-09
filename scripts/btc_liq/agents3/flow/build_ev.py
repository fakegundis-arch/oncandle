import numpy as np, pandas as pd, fast, events, feats, btc_common as bc, time
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
L = fast.Lean(exness=False); P = feats.Pre(L)
mid = np.load(SP + 'mid.npy').astype(np.float64)
m = L.metrics; oi = m.sum_open_interest.to_numpy(); mts = m.ts.to_numpy() - L.t0
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; okr = np.r_[False, np.diff(mts) == 300]; doi[~okr] = np.nan
tvr = m.sum_taker_long_short_vol_ratio.to_numpy()
e = L.eth; eoi = e.sum_open_interest.to_numpy(); ets = e.ts.to_numpy() - L.t0
edoi = np.r_[np.nan, eoi[1:] / eoi[:-1] - 1]; edoi[~np.r_[False, np.diff(ets) == 300]] = np.nan
lo = bc.ts_of('2026-01-01') - L.t0; hi = L.n - 4 * 3600 - 400
fams = [(30, 4), (30, 6), (30, 8), (60, 5), (60, 6), (60, 8), (60, 10), (60, 12), (120, 8), (120, 12), (300, 8), (300, 12), (300, 16)]
H = (300, 900, 1800, 3600, 7200, 14400)
out = []
for fi, (W, X) in enumerate(fams):
    s, d = events.bursts(L.c, L.vol, W, X, 900, lo, hi)
    F = feats.compute(P, s, d)
    F['fam'] = fi; F['W'] = W; F['X'] = X; F['s'] = s; F['d'] = d; F['ts'] = s + L.t0
    ct = ((s - 1 + L.t0) // 300) * 300 - L.t0
    k = np.clip(np.searchsorted(mts, ct), 0, len(mts) - 1); has = mts[k] == ct
    F['doi0'] = np.where(has, doi[k], np.nan)
    F['doi1'] = np.where(has & (k >= 1), doi[np.maximum(k - 1, 0)], np.nan)   # previous bucket
    F['doi_n'] = np.where(has & (k + 1 < len(doi)), doi[np.minimum(k + 1, len(doi) - 1)], np.nan)  # next bucket (known ct+660)
    F['tvr0'] = np.where(has, tvr[k], np.nan)
    ke = np.clip(np.searchsorted(ets, ct), 0, len(ets) - 1)
    F['edoi0'] = np.where(ets[ke] == ct, edoi[ke], np.nan)
    F['sk'] = ct + 360; F['pos'] = s - ct
    v = L.vol[s]
    for h in H:
        F[f'f{h}'] = d * (mid[s + 2 + h] - mid[s + 2]) / v
        F[f'g{h}'] = d * (mid[ct + 362 + h] - mid[ct + 362]) / v
    out.append(F)
    print(W, X, len(F), flush=True)
F = pd.concat(out, ignore_index=True)
F.to_pickle(SP + 'ev.pkl')
