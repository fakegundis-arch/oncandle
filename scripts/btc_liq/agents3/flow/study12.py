import numpy as np, pandas as pd, fast, events, btc_common as bc
L = fast.Lean()
m = L.metrics; oi = m.sum_open_interest.to_numpy(); mts = m.ts.to_numpy() - L.t0
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; okr = np.r_[False, np.diff(mts) == 300]; doi[~okr] = np.nan
lo = bc.ts_of('2026-01-01') - L.t0; hi = L.n - 400
for W, X in ((30, 6), (60, 6), (60, 8), (120, 8), (300, 8), (300, 12)):
    s, d = events.bursts(L.c, L.vol, W, X, 600, lo, hi)
    ct = ((s - 1 + L.t0) // 300) * 300 - L.t0
    k = np.clip(np.searchsorted(mts, ct), 0, len(mts) - 1); dd = np.where(mts[k] == ct, doi[k], np.nan)
    sk = ct + 360 + L.t0
    for name, q, sg in (('follow oiUp.25', dd >= 0.0025, 1), ('follow oiUp.15', dd >= 0.0015, 1), ('fade oiDn.25', dd <= -0.0025, -1), ('follow all', np.isfinite(dd), 1)):
        sig = sk[q]; dirs = sg * d[q]; vol = L.vol[sig - L.t0]
        res = []
        for stop, hold in ((10, 1800), (20, 3600), (20, 7200), (30, 14400)):
            tr = bc.trades(L, sig, dirs, stop_dist=stop * vol, hold=hold)
            a = fast.acct(tr, maxpos=3); st = fast.acct(bc.trades(L, sig, dirs, stop_dist=stop * vol, hold=hold, stress=True), maxpos=3)
            res.append(f"s{stop}h{hold}: n{a['n']} R{a['R']:+.1f} pf{a['pf']:.2f} ${a['final']:.0f} dd{a['dd']:.2f} spf{st['pf']:.2f}")
        print(f'W{W}X{X} {name:15s}', ' | '.join(res))
