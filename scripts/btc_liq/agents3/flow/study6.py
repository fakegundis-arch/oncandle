import numpy as np, pandas as pd, fast, btc_common as bc
L = fast.Lean()
F = pd.read_pickle('cache_oi_feats.pkl')
def run(q, kw, maxpos=1, stress=False):
    s = F.ts[q].to_numpy(); d = F.d[q].to_numpy(); vol = L.vol[s - L.t0]
    kw = {k: (v * vol if k == 'stop_dist' else v) for k, v in kw.items()}
    tr = bc.trades(L, s, d, stress=stress, **kw)
    return tr
V2 = dict(stop_dist=8, tp_r=1.5, hold=300, be_at=1.0, trail=1.0)
for th, mth in ((0.0025, 0.0015), (0.003, 0.0015), (0.004, 0.0015), (0.003, 0.002), (0.005, 0.0015)):
    q = (F.doi <= -th) & (F.mv >= mth)
    for mp in (1, 2, 3):
        tr = run(q, V2); a = fast.acct(tr, maxpos=mp); st = fast.acct(run(q, V2, stress=True), maxpos=mp)
        ja = fast.acct(tr, '2026-01-01', '2026-04-01', maxpos=mp); jb = fast.acct(tr, '2026-04-01', '2026-07-01', maxpos=mp)
        print(th, mth, mp, {k: round(v, 2) for k, v in a.items()}, 'stressPF', round(st['pf'], 2), 'Q1R', round(ja['R'], 1), 'Q2R', round(jb['R'], 1))
