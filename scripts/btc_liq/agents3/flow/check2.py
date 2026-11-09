import numpy as np, pandas as pd, fast, btc_common as bc, strategy
from check import bt, L
for name, p in strategy.CANDIDATES.items():
    t = bt(p, '2026-01-01', '2026-07-01')
    print(name)
    for d in (1, -1):
        q = t[t.dir == d]; a = bc.account(q, '2026-01-01', '2026-07-01', maxpos=p['maxpos'])
        print('  dir', d, 'n', a['n'], 'R', round(a['R'], 1), 'pf', round(a['pf'], 2))
    rows = []
    for m in range(1, 7):
        a, b = f'2026-{m:02d}-01', f'2026-{m + 1:02d}-01'
        q = bt(p, a, b); A = bc.account(q, a, b, maxpos=p['maxpos'])
        rows.append(f"{a[:7]} n{A['n']} R{A['R']:+.1f}")
    print('  per month (account rules):', ' | '.join(rows))
    A = bc.account(t, '2026-01-01', '2026-07-01', maxpos=p['maxpos'])
    print('  r quantiles', np.round(np.percentile(t.r, [5, 25, 50, 75, 95]), 2), 'max r', round(t.r.max(), 2), 'top5 share of R', round(np.sort(t.r)[-5:].sum() / t.r.sum(), 2))
    print('  avg hold min', round(((t.exit_ts - t.entry_ts) / 60).mean(), 1), 'avg stop $', round(t.sd.mean(), 1))
