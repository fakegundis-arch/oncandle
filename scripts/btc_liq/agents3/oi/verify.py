"""Run strategy.backtest in 2-month chunks (memory), stitch, and report with btc_common.account."""
import sys, resource, numpy as np, pandas as pd
import strategy as S, btc_common as bc
D='/home/user/btc_lab_data'
chunks=[('2026-01-01','2026-03-01'),('2026-03-01','2026-05-01'),('2026-05-01','2026-07-01')]
for name,p in S.CANDIDATES.items():
    T={False:[],True:[]}
    for a,b in chunks:
        for stress in (False,True):
            T[stress].append(S.backtest(p,D,a,b,stress))
        print(a,b,'maxrss GB',resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6, flush=True)
    for stress in (False,True):
        t=pd.concat(T[stress]).reset_index(drop=True)
        t.to_csv(f'trades_{name}{"_stress" if stress else ""}.csv',index=False)
        for a,b in [('2026-01-01','2026-07-01'),('2026-01-01','2026-05-01'),('2026-05-01','2026-07-01'),('2026-01-01','2026-04-01'),('2026-04-01','2026-07-01')]:
            print(name,'stress' if stress else 'normal',a,b,{k:round(v,3) for k,v in bc.account(t,a,b,maxpos=p['maxpos']).items()})
        if not stress:
            t['month']=pd.to_datetime(t.entry_ts,unit='s').dt.strftime('%Y-%m')
            print(t.groupby('month').r.agg(['count','sum']).round(2).T.to_string())
