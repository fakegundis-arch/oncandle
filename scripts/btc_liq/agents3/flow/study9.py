import numpy as np, pandas as pd, fast, btc_common as bc
L = fast.Lean()
F = pd.read_pickle('cache_oi_feats.pkl')
q = (F.doi <= -0.003) & (F.mv >= 0.0015)
s = F.ts[q].to_numpy(); d = F.d[q].to_numpy()
for delay in (0, 10, 20, 30, 60, 90, 120, 180, 240):
    vol = L.vol[s + delay - L.t0]
    tr = bc.trades(L, s + delay, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)
    tr2 = bc.trades(L, s + delay, d, stop_dist=8 * vol, hold=300)
    print(delay, len(tr), round(tr.r.mean(), 3), round(tr2.r.mean(), 3))
# when big60 is large, does waiting help?
big = F.big60[q].to_numpy() > np.nanmedian(F.big60[q])
for delay in (0, 30, 60, 120, 240):
    vol = L.vol[s + delay - L.t0]
    tr = bc.trades(L, s + delay, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)
    r = pd.Series(tr.r.to_numpy(), index=tr.sig_ts - delay).reindex(s).to_numpy()
    print('delay', delay, 'big', round(np.nanmean(r[big]), 3), 'small', round(np.nanmean(r[~big]), 3))
