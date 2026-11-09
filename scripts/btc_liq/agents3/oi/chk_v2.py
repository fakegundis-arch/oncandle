import sys, numpy as np, pandas as pd, time
sys.path.insert(0,'.')
import lab, btc_common as bc
ex=lab.Ex()
for mode in ['rule','honest']:
    F=pd.read_parquet(f'feat_{mode}_d0.parquet')
    F=F[(F.s>=bc.ts_of('2026-01-01'))&(F.s<bc.ts_of('2026-07-01'))]
    for mv in ['m5','mtot']:
        for oith, stopk, tp, be, tr, v in [(-0.007,5,2,np.nan,np.nan,'v1'),(-0.005,8,1.5,1,1,'v2')]:
            sel=(F.d5<=oith)&(F[mv].abs()>=0.003)
            if v=='v2': sel&=np.sign(F.nt5)==np.sign(F[mv])
            G=F[sel]
            d=np.sign(G[mv]).astype(int).to_numpy()
            out=ex.run(G.s.to_numpy(), d, stopk*G.vol.to_numpy(), tp, 300, be, tr)
            ok=~np.isnan(out[2])
            res=lab.acct(*[o[ok] for o in out],'2026-01-01','2026-07-01')
            outs=ex.run(G.s.to_numpy(), d, stopk*G.vol.to_numpy(), tp, 300, be, tr, stress=True)
            ok2=~np.isnan(outs[2]); rs=lab.acct(*[o[ok2] for o in outs],'2026-01-01','2026-07-01')
            print(mode, mv, v, {k:round(x,3) for k,x in res.items()}, 'stressPF', round(rs['pf'],2))
