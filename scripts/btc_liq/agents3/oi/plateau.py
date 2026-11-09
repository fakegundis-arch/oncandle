import numpy as np, pandas as pd
import search as S
from outcomes import EXITS, STOPS, A
P,O=S.load(0)
R,X,ent,px,sd=O['R'],O['X'],O['ent'],O['px'],O['sd']
RT=np.ascontiguousarray(R.transpose(1,2,0)); XT=np.ascontiguousarray(X.transpose(1,2,0)); del R,X
stop_of=np.array([e[0] for e in EXITS],np.int64)
ex=pd.DataFrame([(STOPS[k],tp,h,be,tr) for k,tp,h,(be,tr) in EXITS],columns=['stop','tp','hold','be','tr'])
fix=[j for j,e in enumerate(EXITS) if STOPS[e[0]]==4 and e[1]==1.5 and e[2]==600 and e[3][0]==1.0 and e[3][1]==0.5][0]
fix2=[j for j,e in enumerate(EXITS) if STOPS[e[0]]==6 and e[1]==1.5 and e[2]==300 and e[3][0]==1.0 and e[3][1]==1.0][0]
short=np.flatnonzero(ex.hold.to_numpy()<=600)
out=np.zeros((len(EXITS),len(S.COLS)))
rows_out=[]
for of,ov in [('d5',-0.002),('d5',-0.003),('d10',-0.003),('d10',-0.004),('d15',-0.0035),('d15',-0.005),('d30',-0.004),('d30',-0.006),('z5_7d',-2.0),('z5_7d',-3.0)]:
    for mv in [0.003,0.005,0.008]:
        m=(P[of]<=ov)&(P.m5.abs()>=mv)
        rows=np.flatnonzero(m); d=np.sign(P.m5.to_numpy()[rows]); dsel=(d>0).astype(np.int64)
        S.run_exits(rows,dsel,ent,px,sd,RT,XT,stop_of,A,S.MAY,S.APR,out)
        o=pd.DataFrame(out.copy(),columns=S.COLS)
        so=o.iloc[short]
        frac=(so.R>0).mean()
        f=o.iloc[fix]; f2=o.iloc[fix2]
        rows_out.append((of,ov,mv,int(f.n),round(f.R,1),round(f.RJA,1),round(f.RMJ,1),round(f.pf,2),round(f.final),round(f.dd,2), round(f2.R,1),round(f2.RMJ,1), round(frac,2), round(so.R.median(),1)))
print(pd.DataFrame(rows_out,columns=['oi','th','mv','n','R','RJA','RMJ','pf','final','dd','R(s6,300)','RMJ(s6)','frac_short_exits_R>0','median_R_short']).to_string())
