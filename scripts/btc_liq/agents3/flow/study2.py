import numpy as np, pandas as pd, fast, base, btc_common as bc
L = fast.Lean()
m = L.metrics; oi = m.sum_open_interest.to_numpy(); ts = m.ts.to_numpy()
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; ok = np.r_[False, np.diff(ts) == 300]
T = ts - L.t0
good = ok & (T - 400 > 0) & (T + 1200 < L.n) & (ts >= bc.ts_of('2026-01-01'))
mv = np.full(len(T), np.nan); mv[good] = L.c[T[good]] / L.c[T[good] - 300] - 1
sel = np.flatnonzero(good & (doi <= -0.005) & (np.abs(mv) >= 0.003))
# cheat: enter at first second s in bucket where running move from T-300 crosses th in final direction
for th in (0.0015, 0.002, 0.0025, 0.003):
    sig, dirs, lag = [], [], []
    for k in sel:
        t = T[k]; d = int(np.sign(mv[k]))
        run = d * (L.c[t - 300:t + 1] / L.c[t - 300] - 1)
        i = np.flatnonzero(run >= th)
        if len(i) == 0: continue
        s = t - 300 + i[0] + 1
        sig.append(s + L.t0); dirs.append(d); lag.append(t + 60 - s)
    sig = np.array(sig); dirs = np.array(dirs); vol = L.vol[sig - L.t0]
    for hold in (300, 600):
        tr = bc.trades(L, sig, dirs, stop_dist=8 * vol, tp_r=1.5, hold=hold, be_at=1.0, trail=1.0)
        a = fast.acct(tr)
        print(th, hold, 'lag med', np.median(lag), {k: round(v, 2) for k, v in a.items()})
# baseline v2 w/o flow filter
s, d = base.oi_signals(L, 0.005, 0.003, False, 1); vol = L.vol[s - L.t0]
print('V2noflow', fast.acct(bc.trades(L, s, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)))
print('V2noflow at T', fast.acct(bc.trades(L, s-60, d, stop_dist=8 * vol, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)))
