import numpy as np, pandas as pd, time
import lab, search as S
from outcomes import EXITS, STOPS, A
P,O=S.load(0)
R,X,ent,px,sd=O['R'],O['X'],O['ent'],O['px'],O['sd']
RT=np.ascontiguousarray(R.transpose(1,2,0)); XT=np.ascontiguousarray(X.transpose(1,2,0))
stop_of=np.array([e[0] for e in EXITS],np.int64)
m=(P.d5<=-0.003)&(P.m5.abs()>=0.002)
rows=np.flatnonzero(m); d=np.sign(P.m5.to_numpy())[rows]; dsel=(d>0).astype(np.int64)
out=np.zeros((len(EXITS),len(S.COLS)))
t=time.time(); S.run_exits(rows,dsel,ent,px,sd,RT,XT,stop_of,A,S.MAY,S.APR,out); print('t',time.time()-t)
t=time.time(); S.run_exits(rows,dsel,ent,px,sd,RT,XT,stop_of,A,S.MAY,S.APR,out); print('t',time.time()-t, len(rows))
# direct check with btc_common for a few exits
ex=lab.Ex()
s=P.s.to_numpy()[rows]; vol=P.vol.to_numpy()[rows]
for j in [0, 100, 455, 839]:
    ki,tp,hold,(be,tr)=EXITS[j]
    e_,x_,r_,sd_,px_=ex.run(s,d,STOPS[ki]*vol,tp,hold,be,tr)
    ok=~np.isnan(r_)
    a=lab.acct(e_[ok],x_[ok],r_[ok],sd_[ok],px_[ok],'2026-01-01','2026-07-01')
    a1=lab.acct(e_[ok],x_[ok],r_[ok],sd_[ok],px_[ok],'2026-01-01','2026-05-01')
    print(EXITS[j], a, '\n   kernel', dict(zip(S.COLS,out[j].round(4))), '\n   JA', a1)
