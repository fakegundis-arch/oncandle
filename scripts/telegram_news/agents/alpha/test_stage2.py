import numpy as np, pandas as pd
from lib import C, DATA, WORK, lean_ticks
from engine import gaps
from stage2 import outcomes

p = pd.read_pickle(f"{WORK}/posts.pkl")
rng = np.random.default_rng(3)
inst = "gold"
tk = C.load_ticks(inst, DATA)
# lean loader must give identical arrays
lt = lean_ticks(inst)
print("lean == common:", all(np.array_equal(lt[k], tk[k]) for k in lt), len(lt["t"]), len(tk["t"]))
del lt
g = gaps(tk["t"])
sel = rng.choice(len(p), 250, replace=False)
bad = tot = 0
for stress in [False, True]:
    lat = C.LAT_STRESS if stress else C.LAT
    for tp, mh, be, tr in [(None, 600, 0.5, None), (2.0, 3600, 1.0, 0.5), (None, None, None, 1.0), (3.0, 1800, None, None)]:
        dec = p.ts.to_numpy()[sel] + lat
        ds = rng.choice([-1, 1], len(sel)); sds = rng.uniform(0.3, 6, len(sel))
        R, ET, XT, SD = outcomes(tk, g, dec, ds, sds, tp, mh, be, tr, stress)
        for e in range(len(sel)):
            m = C.market_entry(tk, int(dec[e] - lat), int(ds[e]), stress=stress)
            if m is None:
                continue
            i, fill = m
            k, r, sd = C.exit_trade(tk, i, fill, int(ds[e]), float(sds[e]), tp_r=tp, max_hold_s=mh, be_at_r=be, trail_r=tr, stress=stress)
            tot += 1
            if int(tk["t"][k]) != XT[e] or abs(r - R[e]) > 1e-6:
                bad += 1
                if bad < 5: print("MISMATCH", e, k, r, R[e])
print("checked", tot, "mismatches", bad)
