import time
from monthly import U, R, X, Fz, Fo, ev, ST, ex_index, fidx
from search import trades_for, evaluate
import numpy as np, pandas as pd
import strategy as S, common as C
D = '/home/user/news_lab_data'
t0 = time.time()
p = S.CANDIDATES['gold_shock_pullback']
tr = S.backtest(p, D, '2025-01-01', '2026-07-01')
print('strategy trades', len(tr), f'{time.time()-t0:.0f}s')
rw = dict(style=ST.index(('P', 0, 0.5, 600)), L=30, mode=1, fi=fidx((3, 'any', 0, 0, 'any', 1, 1)), exit=ex_index(4.5, -1.0, -1.0, np.inf, 14400))
pre = trades_for(U, R, X, Fz, Fo, ev, rw)
pre['post_ts'] = ev.ts.to_numpy()[pre.ev]
m = tr.merge(pre, on=['post_ts'], how='outer', suffixes=('', '_pre'), indicator=True)
print(m._merge.value_counts())
both = m[m._merge == 'both']
print('max |r diff|', np.abs(both.r - both.r_pre).max(), 'entry diff', (both.entry_ts != both.entry_ts_pre).sum(), 'exit diff', (both.exit_ts != both.exit_ts_pre).sum(), 'dir diff', (both.dir != both.dir_pre).sum())
print(m[m._merge != 'both'][['post_ts', 'entry_ts', 'r', 'entry_ts_pre', 'r_pre', '_merge']].assign(t=lambda d: pd.to_datetime(d.post_ts, unit='s')).to_string())
for a, b in [('2025-01-01', '2026-05-01'), ('2026-05-01', '2026-07-01'), ('2026-01-01', '2026-07-01')]:
    print(a, b, C.metrics(tr, a, b))
