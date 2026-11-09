import numpy as np, pandas as pd, fast, btc_common as bc, strategy
L = fast.Lean()
a, b = bc.ts_of('2026-01-01'), bc.ts_of('2026-07-01')
for name, p in strategy.CANDIDATES.items():
    sig, d = strategy.signals(L, p, '2026-01-01', '2026-07-01')
    Rs, Fs = [], []
    for k in range(100):
        rng = np.random.default_rng(1000 + k)
        sh = rng.integers(1, 15, len(sig)) * 86400 * rng.choice([-1, 1], len(sig))
        t = sig + sh; bad = (t < a) | (t >= b - 4 * 3600); t[bad] = sig[bad] - sh[bad]
        o = np.argsort(t); t, dd = t[o], d[o]
        vol = L.vol[t - L.t0]
        tr = bc.trades(L, t, dd, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=p['hold'])
        A = bc.account(tr, '2026-01-01', '2026-07-01', maxpos=p['maxpos'])
        Rs.append(A['R']); Fs.append(A['final'])
    Rs, Fs = np.array(Rs), np.array(Fs)
    print(name, 'shifted-signal null (100 runs): R mean', round(Rs.mean(), 1), 'sd', round(Rs.std(), 1), 'max', round(Rs.max(), 1),
          '95th', round(np.percentile(Rs, 95), 1), '| final median', round(np.median(Fs)), 'max', round(Fs.max()))
