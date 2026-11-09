import numpy as np, pandas as pd
F = pd.read_pickle('cache_oi_feats.pkl')
F['month'] = pd.to_datetime(F.ts, unit='s').dt.month
pd.set_option('display.width', 200)
F['doib'] = pd.cut(-F.doi, [0.0025, 0.003, 0.004, 0.005, 0.007, 0.01, 1])
F['mvb'] = pd.cut(F.mv, [0.0015, 0.002, 0.0025, 0.003, 0.004, 0.006, 1])
print(F.pivot_table(index='doib', columns='mvb', values='v2', aggfunc='sum').round(1))
print(F.pivot_table(index='doib', columns='mvb', values='v2', aggfunc='count'))
print(F.pivot_table(index='doib', columns='month', values='v2', aggfunc='sum').round(1))
for col in ('big60', 'big30', 'v30', 'eoi_lastchg', 'r60', 'r20', 'imb60', 'dep_imb', 'eff30', 'tlsr', 'prem_d', 'nOIdrop1h', 'doi_prev', 'vol_rel', 'r300', 'brk4h', 'big60_rel', 'asz60'):
    try: q = pd.qcut(F[col], 4, duplicates='drop')
    except Exception as e: print(col, e); continue
    g = F.groupby(q, observed=True)
    print(col, ' | '.join(f'{str(k)}: n{len(v)} v2 {v.v2.mean():+.3f} h600 {v.h600.mean():+.3f}' for k, v in g))
