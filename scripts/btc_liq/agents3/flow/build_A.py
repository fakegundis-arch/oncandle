"""family A: burst (W, X) -> decision when the open interest of the bucket holding the burst is known (ct + 360)."""
import numpy as np, pandas as pd, fast, events, feats, slib, btc_common as bc, sys, time
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
fake = int(sys.argv[1]) if len(sys.argv) > 1 else -1      # -1 real, k>=0 fake seed
L = fast.Lean()
m = L.metrics; oi = m.sum_open_interest.to_numpy(); mts = m.ts.to_numpy() - L.t0
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; okr = np.r_[False, np.diff(mts) == 300]; doi[~okr] = np.nan
e = L.eth; eoi = e.sum_open_interest.to_numpy(); ets = e.ts.to_numpy() - L.t0
edoi = np.r_[np.nan, eoi[1:] / eoi[:-1] - 1]; edoi[~np.r_[False, np.diff(ets) == 300]] = np.nan
lo = bc.ts_of('2026-01-01') - L.t0 - 400; hi = bc.ts_of('2026-07-01') - L.t0 - 400
fams = [(30, 5), (30, 6), (30, 8), (60, 6), (60, 7), (60, 8), (60, 10), (120, 8), (120, 10), (120, 12), (300, 10), (300, 12), (300, 16)]
grid = [(k, tp, h, be, tr) for k in (10, 15, 20, 30) for h in (1800, 3600, 7200, 14400) for tp in (np.nan, 3.0)
        for (be, tr) in ((np.nan, np.nan), (1.0, 1.5))]
rows = []
for fi, (W, X) in enumerate(fams):
    s, d = events.bursts(L.c, L.vol, W, X, 900, lo, hi)
    ct = ((s - 1 + L.t0) // 300) * 300 - L.t0
    k = np.clip(np.searchsorted(mts, ct), 0, len(mts) - 1); has = mts[k] == ct
    d0 = np.where(has, doi[k], np.nan); d1 = np.where(has & (k >= 1), doi[np.maximum(k - 1, 0)], np.nan)
    ke = np.clip(np.searchsorted(ets, ct), 0, len(ets) - 1); e0 = np.where(ets[ke] == ct, edoi[ke], np.nan)
    sk = ct + 360
    keep = np.isfinite(d0) & (d0 >= -0.004)
    df = pd.DataFrame(dict(fam=fi, W=W, X=X, s=s[keep], d=d[keep], sk=sk[keep], doi0=d0[keep], doi1=d1[keep], edoi0=e0[keep]))
    df['z'] = df.d * (L.c[df.sk - 1] - L.c[df.s - 1]) / L.vol[df.s]
    df['lag'] = df.sk - df.s
    rows.append(df)
D = pd.concat(rows, ignore_index=True)
# flow features at the burst second (known at s <= sk)
P = feats.Pre(L)
Fx = feats.compute(P, D.s.to_numpy(), D.d.to_numpy())
for c in ('big30', 'big60', 'big60_rel', 'v60', 'v300', 'imb60', 'imb300', 'eff60', 'eff300', 'asz60', 'dep_hit_rel', 'dep_imb',
          'brk4h', 'brk24h', 'prem_d', 'prem_dir', 'vol_rel', 'oi_4h', 'oi_24h', 'lsr', 'tlsr', 'fund', 'r900'):
    D[c] = Fx[c].to_numpy()
del P, Fx
D['sig'] = D.sk + L.t0
if fake >= 0:
    rng = np.random.default_rng(fake)
    sh = rng.integers(1, 15, len(D)) * 86400 * rng.choice([-1, 1], len(D))
    t = D.sig.to_numpy() + sh
    a, b = bc.ts_of('2026-01-01'), bc.ts_of('2026-07-01') - 15 * 3600
    bad = (t < a) | (t >= b); t[bad] = D.sig.to_numpy()[bad] - sh[bad]
    D['sig'] = t
D = D.sort_values(['sig', 'fam']).reset_index(drop=True)
t0 = time.time()
E, Xx, R, S, Px = slib.outcomes(L, D.sig.to_numpy(), D.d.to_numpy(), grid)
_, _, Rs, _, _ = slib.outcomes(L, D.sig.to_numpy(), D.d.to_numpy(), grid, stress=True)
print('outcomes', time.time() - t0, len(D), flush=True)
tag = 'real' if fake < 0 else f'fake{fake}'
D.to_pickle(SP + f'A_{tag}.pkl')
np.savez_compressed(SP + f'A_{tag}_out.npz', E=E, X=Xx, R=R.astype(np.float32), S=S.astype(np.float32), P=Px.astype(np.float32), Rs=Rs.astype(np.float32), grid=np.array(grid))
