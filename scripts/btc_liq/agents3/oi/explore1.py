import sys, numpy as np, pandas as pd
sys.path.insert(0,'.')
from prep import load_binance
import btc_common as bc
t0,n,c,bq,sq=load_binance('2025-12-01','2026-07-01')
F=pd.read_parquet('feat_honest_d0.parquet')
F=F[(F.s>=bc.ts_of('2026-01-01'))&(F.s<bc.ts_of('2026-06-30'))].copy()
si=F.s.to_numpy()-t0+2
for h in [60,120,300,600,900,1800,3600]:
    F[f'f{h}']=c[si+h]-c[si]
F['dir']=np.sign(F.m5)
F.to_parquet('/tmp/claude-0/-home-user-oncandle/d4b1cdef-7862-509b-82d4-a440bb0031e4/scratchpad/fwd.parquet')
def show(mask, name, d=None):
    G=F[mask]
    dd=G.dir if d is None else d[mask]
    row=[name, len(G)]
    for h in [60,120,300,600,900,1800,3600]:
        x=(G[f'f{h}']*dd)/G.vol
        row.append(f'{x.mean():+.2f}/{(x>0).mean():.2f}')
    print(*row)
print('follow dir = sign(m5) ; mean fwd move in vol units / hit rate; horizons 1,2,5,10,15,30,60 min')
for oth in [0, -0.002,-0.003,-0.005,-0.007,-0.01]:
    for mth in [0.002,0.003,0.005,0.008]:
        show((F.d5<=oth)&(F.m5.abs()>=mth), f'd5<={oth} |m5|>={mth}')
print('OI rising')
for oth in [0.002,0.003,0.005]:
    for mth in [0.002,0.003,0.005]:
        show((F.d5>=oth)&(F.m5.abs()>=mth), f'd5>={oth} |m5|>={mth}')
