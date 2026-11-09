import numpy as np, pandas as pd, fast, btc_common as bc, strategy
L = fast.Lean()
A, B = '2026-01-01', '2026-07-01'
for name, p in strategy.CANDIDATES.items():
    lo = bc.ts_of(A) - 86400 - L.t0; hi = bc.ts_of(B) - L.t0
    s, d = strategy._bursts(L.c, L.vol, p['W'], p['X'], p['refr'], lo, hi)
    sig, dd = strategy.signals(L, p, A, B)
    # map each signal to its burst second
    ct = sig - 360; bs = np.array([s[(s - 1 + L.t0 >= c) & (s - 1 + L.t0 < c + 300)][0] for c in ct])
    lag = sig - (bs + L.t0)
    vol = L.vol[sig - L.t0]
    t = bc.trades(L, sig, dd, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=p['hold'])
    lagm = dict(zip(sig, lag)); t['lag'] = t.sig_ts.map(lagm)
    t['lagb'] = pd.cut(t.lag, [0, 150, 240, 361])
    print(name); print(t.groupby('lagb', observed=True).r.agg(['count', 'sum', 'mean']).round(2))
    # retrace between burst and decision
    ret = dd * (L.c[sig - L.t0 - 1] - L.c[bs - 1]) / L.vol[bs]
    print('  move from burst to decision (vol units): mean', round(ret.mean(), 2), 'median', round(np.median(ret), 2))
    # alternative entries: fixed delays after the burst for OI-confirmed bursts (decision >= OI known time)
    for delay in (0, 60, 120, 180, 300, 600):
        sg = np.maximum(bs + L.t0 + delay, sig)   # cannot enter before OI known
        t2 = bc.trades(L, sg, dd, stop_dist=p['stop'] * L.vol[sg - L.t0], tp_r=p['tp'], hold=p['hold'])
        a = bc.account(t2, A, B, maxpos=p['maxpos'])
        print(f'  entry max(burst+{delay}s, OI known): n{a["n"]} R{a["R"]:+.1f} ${a["final"]:.0f} dd{a["dd"]:.2f}')
