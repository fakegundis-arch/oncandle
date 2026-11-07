import numpy as np, pandas as pd
from lib import WORK
p = pd.read_pickle(f"{WORK}/posts.pkl")
p["m"] = pd.to_datetime(p.ts, unit="s").dt.strftime("%Y-%m")
for inst in ["gold", "nasdaq"]:
    b = np.load(f"{WORK}/base_{inst}.npz")
    P, offs, v = b["P"], list(b["offs"]), b["vol60"]
    c = lambda o: P[:, offs.index(o)]
    pre = (c(2) - c(-10)) / v
    pre60 = (c(-10) - c(-120)) / v
    print("=====", inst, "median vol60", np.nanmedian(v), "spr", np.nanmedian(b["spr"]))
    for H in [10, 30, 60, 120, 300, 900, 1800]:
        f = (c(H) - c(2)) / v
        ok = ~np.isnan(pre) & ~np.isnan(f)
        out = [f"H={H:5d} corr(pre,f)={np.corrcoef(pre[ok], f[ok])[0,1]:+.3f}"]
        for th in [1, 2, 4, 8]:
            s = ok & (np.abs(pre) > th)
            out.append(f"|pre|>{th}: n={s.sum():5d} mean sgn*f={np.mean(np.sign(pre[s])*f[s]):+.3f} hit={np.mean(np.sign(pre[s])*f[s]>0):.2f}")
        print("  ".join(out))
    # absolute move after post vs quiet baseline
    a = np.abs(c(300) - c(2)) / v
    print("median |300s move|/vol60 all", np.nanmedian(a))
