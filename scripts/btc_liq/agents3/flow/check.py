"""full-period check of strategy candidates via the verified lean loader (identical arrays to btc_common.Market)."""
import numpy as np, pandas as pd, fast, btc_common as bc, strategy, sys, json
L = fast.Lean()
def bt(p, start, end, stress=False):
    sig, d = strategy.signals(L, p, start, end)
    vol = L.vol[sig - L.t0]
    t = bc.trades(L, sig, d, stop_dist=p['stop'] * vol, tp_r=p.get('tp', np.nan), hold=p['hold'], be_at=p.get('be', np.nan),
                  trail=p.get('trail', np.nan), stress=stress)
    a, b = bc.ts_of(start), bc.ts_of(end)
    return t[(t.entry_ts >= a) & (t.entry_ts < b)].sort_values(['entry_ts', 'sig_ts']).reset_index(drop=True)
def report(name, p):
    out = {}
    for lab, a, b in (('Jan-Apr', '2026-01-01', '2026-05-01'), ('May-Jun', '2026-05-01', '2026-07-01'), ('Jan-Jun', '2026-01-01', '2026-07-01'),
                      ('Jan-Mar', '2026-01-01', '2026-04-01'), ('Apr-Jun', '2026-04-01', '2026-07-01')):
        t = bt(p, a, b); ts = bt(p, a, b, True)
        A = bc.account(t, a, b, maxpos=p['maxpos']); S = bc.account(ts, a, b, maxpos=p['maxpos'])
        out[lab] = dict(n=A['n'], R=round(A['R'], 2), pf=round(A['pf'], 2), win=round(A['win'], 3), final=round(A['final']), dd=round(A['dd'], 3),
                        max_lot=round(A['max_lot'], 2), stress_pf=round(S['pf'], 2), stress_final=round(S['final']))
    t = bt(p, '2026-01-01', '2026-07-01')
    t['m'] = pd.to_datetime(t.entry_ts, unit='s').dt.strftime('%Y-%m')
    out['monthR_all_signals'] = t.groupby('m').r.sum().round(2).to_dict()
    out['monthN_all_signals'] = t.groupby('m').size().to_dict()
    print(name, json.dumps(out, indent=1))
    return out
if __name__ == '__main__':
    for name, p in strategy.CANDIDATES.items():
        report(name, p)
