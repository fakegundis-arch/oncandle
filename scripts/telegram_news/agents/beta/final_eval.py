import time, json
import numpy as np, pandas as pd
import strategy as S, common as C
D = '/home/user/news_lab_data'
P = [('search 2025-01..2026-04', '2025-01-01', '2026-05-01'), ('check 2026-05..06', '2026-05-01', '2026-07-01'), ('Jan-Jun 2026', '2026-01-01', '2026-07-01')]
out = {}
for nm, p in S.CANDIDATES.items():
    t0 = time.time()
    tr = S.backtest(p, D, '2025-01-01', '2026-07-01')
    trs = S.backtest(p, D, '2025-01-01', '2026-07-01', stress=True)
    res = {}
    for lab, a, b in P:
        m = C.metrics(tr, a, b); ms = C.metrics(trs, a, b)
        res[lab] = dict(n=m['n'], R=round(m['R'], 1), pf=round(m['pf'], 2), win=round(m['win'], 3), final=round(float(m['final']), 0),
                        dd=round(float(m['dd']), 3), max_lot=round(float(m['max_lot']), 2), taken=m['taken'], skipped=m['skipped'],
                        stress_pf=round(ms['pf'], 2), stress_R=round(ms['R'], 1), stress_final=round(float(ms['final']), 0))
    tr['m'] = pd.to_datetime(tr.entry_ts, unit='s').dt.strftime('%Y-%m')
    trs['m'] = pd.to_datetime(trs.entry_ts, unit='s').dt.strftime('%Y-%m')
    pm = tr.groupby('m').r.agg(['size', 'sum']).round(1)
    pms = trs.groupby('m').r.sum().round(1)
    res['per_month'] = {m: (int(n), float(s), float(pms.get(m, np.nan))) for m, (n, s) in pm.iterrows()}
    res['long_short_R'] = (round(tr.r[tr.dir > 0].sum(), 1), round(tr.r[tr.dir < 0].sum(), 1), int((tr.dir > 0).sum()), int((tr.dir < 0).sum()))
    out[nm] = res
    tr.to_csv(f'cache/trades_{nm}.csv', index=False)
    print(nm, f'{time.time()-t0:.0f}s')
    for k, v in res.items():
        print('  ', k, v)
json.dump(out, open('cache/final_eval.json', 'w'), indent=1, default=str)
