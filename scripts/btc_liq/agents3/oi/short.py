import numpy as np, pandas as pd, sys
from outcomes import EXITS, STOPS
from analyze import ex_str
ex=pd.DataFrame([(STOPS[k],tp,h,f'{be}/{tr}') for k,tp,h,(be,tr) in EXITS],columns=['stop','tp','hold','trail'])
s=int(sys.argv[1]); hmax=int(sys.argv[2])
df=pd.read_parquet(f's1f_{s}.parquet')
d=pd.read_parquet(f's1defs_{s}.parquet')
df=df.join(ex,on='exit')
r4=df[(df.n>=40)&(df.pf>=1.3)&(df.RQ1>0)&(df.RQ2>0)&(df.dd>-0.35)&(df.hold<=hmax)]
print(len(r4))
r4=r4.join(d,on='def')
print(r4.groupby(['fade','flt']).size().sort_values(ascending=False).head(10))
print(r4.groupby(['oi_f','oi_v']).size().sort_values(ascending=False).head(10))
for col in ['R','final']:
    top=r4.sort_values(col,ascending=False).head(12)
    for _,r in top.iterrows():
        print(f"{r.oi_f}<={r.oi_v} |{r.mv_f}|>={r.mv_v} fade={r.fade} {r.flt}{'>=' if r.side==1 else '<='}{r.th:.4g} | {ex_str(r.exit)} | JA n{r.nJA:.0f} R{r.RJA:.1f} pf{r.pfJA:.2f} ${r.fJA:.0f} | MJ n{r.nMJ:.0f} R{r.RMJ:.1f} pf{r.pfMJ:.2f} ${r.fMJ:.0f} | ALL n{r.n:.0f} R{r.R:.1f} pf{r.pf:.2f} ${r.final:.0f} dd{r.dd:.2f}")
