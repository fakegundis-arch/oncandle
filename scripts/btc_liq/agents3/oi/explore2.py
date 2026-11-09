import numpy as np, pandas as pd
F=pd.read_parquet('/tmp/claude-0/-home-user-oncandle/d4b1cdef-7862-509b-82d4-a440bb0031e4/scratchpad/fwd.parquet')
F['month']=pd.to_datetime(F.s,unit='s').dt.month
d=F.dir
feats=['d5','d10','d15','d30','d60','accel','ndrop','z5_1d','z5_7d','z15_7d','oi_rel7d','oi_rel1d','e5','e15','ez5_7d','lsr','lsr_c5','lsr_c60','lsr_z7d','tacc','tacc_c60','tacc_z7d','tpos','tpos_c60','tpos_z7d','taker','fund','prem','prem60','prem480','prem_z','m5','m15','m60','mlag','imb5','ntlag','vrel5','rng5','volreg','hour','dimb1','dimb2']
for name, mask in [('|m5|>=.2%', F.m5.abs()>=0.002), ('d5<=-.2%', F.d5<=-0.002), ('d5<=-.2% & |m5|>=.2%', (F.d5<=-0.002)&(F.m5.abs()>=0.002))]:
    G=F[mask & (F.month<=4)]
    print('=====',name,len(G))
    rows=[]
    for f in feats:
        x=G[f].astype(float)
        # signed features: those that are directional get multiplied by dir
        xs = x*G.dir if f in ('m5','m15','m60','mlag','imb5','ntlag','dimb1','dimb2','prem','prem60','prem480','prem_z','fund','lsr_c5','lsr_c60','lsr_z7d','tacc_c60','tacc_z7d','tpos_c60','tpos_z7d') else x
        r=[]
        for h in [300,900,1800,3600]:
            y=G[f'f{h}']*G.dir/G.vol
            g=np.isfinite(xs)&np.isfinite(y)
            r.append(np.corrcoef(xs[g].rank(),y[g].rank())[0,1])
        rows.append((f,*r))
    R=pd.DataFrame(rows,columns=['f','c5','c15','c30','c60']).set_index('f')
    print(R.round(3).to_string())
