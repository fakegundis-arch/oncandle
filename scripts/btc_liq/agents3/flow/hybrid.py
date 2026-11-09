"""angle check: enter at the burst itself (before open interest is known), cut at ct+360 if open interest fell."""
import numpy as np, pandas as pd, fast, btc_common as bc, strategy
L = fast.Lean()
p = dict(strategy.CANDIDATES['flow_bigprint_oiup_30s'])
A, B = '2026-01-01', '2026-07-01'
# all bursts with big print, no OI filter: reuse signals() with oi_up=-1 to get decision ct+360, recompute burst second
lo = bc.ts_of(A) - 86400 - L.t0; hi = bc.ts_of(B) - L.t0
s, d = strategy._bursts(L.c, L.vol, p['W'], p['X'], p['refr'], lo, hi)
mb = L.raw['mb'].astype(float); ms = L.raw['ms'].astype(float)
rel = np.where(d > 0, strategy._rmax(mb, s, 60), strategy._rmax(ms, s, 60)) / np.maximum(strategy._rmax(np.maximum(mb, ms), s, 3600), 1e-9)
m = L.metrics; mts = m.ts.to_numpy(np.int64); oi = m.sum_open_interest.to_numpy(float)
doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]; doi[~np.r_[False, np.diff(mts) == 300]] = np.nan
ct = ((s - 1 + L.t0) // 300) * 300; k = np.clip(np.searchsorted(mts, ct), 0, len(mts) - 1); has = mts[k] == ct
d0 = np.where(has, doi[k], np.nan)
ok = has & (rel > p['big_rel']) & (s + L.t0 >= bc.ts_of(A))
s, d, d0, ct = s[ok], d[ok], d0[ok], ct[ok]
sig = s + L.t0
vol = L.vol[s]
def acct(t): return bc.account(t, A, B, maxpos=p['maxpos'])
t0 = bc.trades(L, sig, d, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=p['hold'])
a = acct(t0); print('enter at burst, no OI filter:', a['n'], round(a['R'], 1), round(a['pf'], 2), round(a['final']), round(a['dd'], 2))
# hybrid: OI fails -> exit at ct+362
fail = ~(d0 >= p['oi_up'])
e = dict(zip(t0.sig_ts, t0.entry_ts))
hold = np.array([p['hold'] if not f else max(int(c + 362 - e.get(x, x + 2)), 1) for x, c, f in zip(sig, ct, fail)])
t1 = bc.trades(L, sig, d, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=hold)
a = acct(t1); print('enter at burst, cut when OI not up:', a['n'], round(a['R'], 1), round(a['pf'], 2), round(a['final']), round(a['dd'], 2))
t1s = bc.trades(L, sig, d, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=hold, stress=True); print('  stress pf', round(acct(t1s)['pf'], 2))
q = t1[np.isin(t1.sig_ts, sig[fail])]; print('  cut trades', len(q), 'R', round(q.r.sum(), 1), '| kept', len(t1) - len(q), 'R', round(t1.r.sum() - q.r.sum(), 1))
# C1 reference: entry at ct+360 only if OI up
sig2 = ct[~fail] + 360; t2 = bc.trades(L, sig2, d[~fail], stop_dist=p['stop'] * L.vol[sig2 - L.t0], tp_r=p['tp'], hold=p['hold'])
a = acct(t2); print('C1 (wait for OI):', a['n'], round(a['R'], 1), round(a['pf'], 2), round(a['final']), round(a['dd'], 2))
