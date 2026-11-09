import numpy as np, pandas as pd
from outcomes import EXITS, STOPS
ex=pd.DataFrame([(STOPS[k],tp,h,f'{be}/{tr}') for k,tp,h,(be,tr) in EXITS],columns=['stop','tp','hold','trail'])
res={}
for s in [0,1,2,3]:
    df=pd.read_parquet(f's1f_{s}.parquet',columns=['def','exit','n','R','pf','RQ1','RQ2','dd','final','nJA','RJA','pfJA'])
    d=pd.read_parquet(f's1defs_{s}.parquet')
    r4=df[(df.n>=40)&(df.pf>=1.3)&(df.RQ1>0)&(df.RQ2>0)]
    r4=r4.join(d,on='def').join(ex,on='exit')
    out={}
    for g in ['fade','hold','oi_f','mv_f','stop']:
        out[g]=r4.groupby(g).size()
    out['flt']=r4.groupby('flt').size().sort_values(ascending=False).head(15)
    res[s]=out
    del df
for g in ['fade','hold','oi_f','mv_f','stop','flt']:
    print('=====',g)
    print(pd.concat({s:res[s][g] for s in res},axis=1).fillna(0).astype(int).to_string())
