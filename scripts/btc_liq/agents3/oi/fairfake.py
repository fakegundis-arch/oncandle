"""Luck check for the short-hold no-filter family with the vol artefact removed: fake signal = real signal shifted by
+-1..14 days, same direction, stop distance from the REAL signal's vol (so spread cost in R is the same as real)."""
import sys, numpy as np, pandas as pd
import lab, search as S
from outcomes import EXITS, STOPS, A, pool_of, shifted_times
F=pd.read_parquet('feat_honest_d0.parquet')
P=F[pool_of(F)].reset_index(drop=True)
short=[j for j,e in enumerate(EXITS) if e[2]<=600]
EX=[EXITS[j] for j in short]
stop_of=np.array([e[0] for e in EX],np.int64)
ex=lab.Ex()
res=[]
for seed in [0,1,2,3]:
    s=P.s.to_numpy(np.int64)
    if seed: s=shifted_times(s,seed)
    vol=P.vol.to_numpy()
    n=len(P); R=np.full((n,2,len(EX)),np.nan); X=np.zeros((n,2,len(EX)),np.int64); ent=np.zeros((n,2),np.int64); px=np.zeros((n,2)); sd=np.zeros((len(STOPS),n))
    for di,d in enumerate((-1,1)):
        for j,(ki,tp,hold,(be,tr)) in enumerate(EX):
            e_,x_,r_,sd_,px_=ex.run(s,d,STOPS[ki]*vol,tp,hold,be,tr)
            R[:,di,j]=r_; X[:,di,j]=x_-A
            if j==0: ent[:,di]=e_; px[:,di]=px_
            sd[ki]=np.where(sd_>0,sd_,sd[ki])
    out=np.zeros((len(EX),len(S.COLS)))
    best=(-99,0,None)
    cnt=0
    for of,ov in S.OICONDS:
        mo=(P.d5>=ov) if of=='d5up' else (P[of]<=ov)
        for mf,mv in S.MOVES:
            m=mo&(P[mf].abs()>=mv)&(P[mf]!=0)
            for fade in (0,1):
                rows=np.flatnonzero(m)
                if len(rows)<30: continue
                d=np.sign(P[mf].to_numpy()[rows])*(-1 if fade else 1); dsel=(d>0).astype(np.int64)
                o=np.argsort(ent[rows,dsel],kind='stable'); rows,dsel=rows[o],dsel[o]
                S.run_exits(rows,dsel,ent,px,sd,R,X,stop_of,A,S.MAY,S.APR,out)
                cnt+=len(EX)
                ok=(out[:,9]>=40)&(out[:,11]>=1.3)&(out[:,14]>0)&(out[:,15]>0)&(out[:,13]>-0.35)
                if ok.any():
                    j=np.flatnonzero(ok)[np.argmax(out[ok,10])]
                    if out[j,10]>best[0]: best=(out[j,10],out[j,12],(of,ov,mf,mv,fade,EX[j]))
    print('seed',seed,'settings',cnt,'best rule-4 R',round(best[0],1),'$',round(best[1]),best[2],flush=True)
