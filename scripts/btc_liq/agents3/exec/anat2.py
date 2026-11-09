import numpy as np, pandas as pd
import lab, features
from lab import bc
L = lab.Lab()
f = features.build(L, oi_th=1.0, mv_th=0.001)   # all buckets with |move| >= 0.1 %
f = f[(f.dec >= bc.ts_of("2026-01-01")) & (f.dec < bc.ts_of("2026-07-01"))].reset_index(drop=True)
f.to_parquet("sig_all.parquet")
T_ = L.tk["t"]; mid = 0.5*(L.tk["bid_last"]+L.tk["ask_last"])
def at(ts):
    q = np.searchsorted(T_, ts, side="right")-1
    return mid[np.clip(q,0,len(mid)-1)]
e = f.dec.to_numpy()+2
for h in (120, 240, 600):
    f[f"g{h}"] = f.dir*(at(e+h)-at(e))/f.vol
f["cost"] = 2*f.spread/f.vol
f["oib"] = pd.cut(f.doi, [-1,-0.007,-0.005,-0.004,-0.003,-0.002,-0.0015,-0.001,-0.0005,0,0.001,0.003,1])
f["mvb"] = pd.cut(f.mv_abs, [0.001,0.0015,0.002,0.003,0.005,1])
pd.set_option("display.width",250)
print(f.pivot_table(index="oib", columns="mvb", values="g240", aggfunc="mean", observed=False).round(2))
print(f.pivot_table(index="oib", columns="mvb", values="g240", aggfunc="count", observed=False))
print(f.pivot_table(index="oib", columns="mvb", values="g600", aggfunc="mean", observed=False).round(2))
print("cost median", f.cost.median())
f["netp"] = f.net>0
print(f.pivot_table(index="oib", columns="netp", values="g240", aggfunc="mean", observed=False).round(2))
