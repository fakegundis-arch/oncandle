import numpy as np, pandas as pd, sys
from outcomes import EXITS, STOPS
from analyze import ex_str
ex=pd.DataFrame([(STOPS[k],tp,h,be,tr) for k,tp,h,(be,tr) in EXITS],columns=['stop','tp','hold','be','tr'])
df=pd.read_parquet('s1f_0.parquet')
d=pd.read_parquet('s1defs_0.parquet')
df=df.join(ex,on='exit')
df=df[(df.hold<=600)]
df=df.join(d,on='def')
df=df[df.fade==0]
ja=df[(df.nJA>=27)&(df.pfJA>=1.3)&(df.ddJA>-0.35)]
print(len(ja))
top=ja.sort_values('fJA',ascending=False).head(25)
for _,r in top.iterrows():
    print(f"{r['def']} {r.oi_f}<={r.oi_v} |{r.mv_f}|>={r.mv_v} {r.flt}{'>=' if r.side==1 else '<='}{r.th:.4g} | {ex_str(r.exit)} | JA n{r.nJA:.0f} R{r.RJA:.1f} pf{r.pfJA:.2f} ${r.fJA:.0f} dd{r.ddJA:.2f} | MJ n{r.nMJ:.0f} R{r.RMJ:.1f} pf{r.pfMJ:.2f} ${r.fMJ:.0f} | ALL n{r.n:.0f} R{r.R:.1f} pf{r.pf:.2f} ${r.final:.0f} dd{r.dd:.2f}")
# how do top-JA picks do in MJ on average (selection honesty)
for k in [10,50,200,1000]:
    t=ja.sort_values('fJA',ascending=False).head(k)
    print(k, 'MJ R mean',round(t.RMJ.mean(),2),'frac>0',round((t.RMJ>0).mean(),2),'MJ $ median',round(t.fMJ.median()))
# no extra filter only
nf=ja[ja.flt=='none'].sort_values('fJA',ascending=False).head(15)
print('--- no extra filter')
for _,r in nf.iterrows():
    print(f"{r.oi_f}<={r.oi_v} |{r.mv_f}|>={r.mv_v} | {ex_str(r.exit)} | JA n{r.nJA:.0f} R{r.RJA:.1f} pf{r.pfJA:.2f} ${r.fJA:.0f} dd{r.ddJA:.2f} | MJ n{r.nMJ:.0f} R{r.RMJ:.1f} pf{r.pfMJ:.2f} ${r.fMJ:.0f} | ALL n{r.n:.0f} R{r.R:.1f} pf{r.pf:.2f} ${r.final:.0f} dd{r.dd:.2f}")
