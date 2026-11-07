import numpy as np, time, pandas as pd
from lib import C, DATA, WORK
from engine import gaps
from engine2 import oco_outcomes
p = pd.read_pickle(f"{WORK}/posts.pkl")
rng = np.random.default_rng(1)
tps = np.array([1.0, 2.0, np.inf]); timers = np.array([60, 600])
for inst in ["gold"]:
    tk = C.load_ticks(inst, DATA); T = tk["t"]; g = gaps(T)
    sel = rng.choice(len(p), 400, replace=False)
    for stress in [False, True]:
        lat = C.LAT_STRESS if stress else C.LAT
        dec = p.ts.to_numpy()[sel] + lat
        sc = 1.0
        up = rng.uniform(0.05, 1.0, len(sel)) * sc; dn = rng.uniform(0.05, 1.0, len(sel)) * sc
        sds = rng.uniform(0.2, 3, len(sel)); E = 120
        i0, R, X, J, D, SD = oco_outcomes(tk, g, dec, up, dn, sds, E, tps, timers, stress=stress)
        bad = tot = both = 0
        for e in range(len(sel)):
            i = C.bar_at(tk, int(dec[e]))
            if i is None: assert i0[e] < 0; continue
            ref = 0.5 * (tk["ask_first"][i] + tk["bid_first"][i])
            pe = C.pending_entry(tk, i, [("stop", 1, ref + up[e]), ("stop", -1, ref - dn[e])], E, stress=stress)
            if pe is None:
                if J[e] >= 0: bad += 1; print("entry mismatch", e)
                continue
            j, legs = pe
            if len(legs) > 1: both += 1
            for q, tp in enumerate(tps):
                for h, H in enumerate(timers):
                    res = [C.exit_trade(tk, j, f, d, float(sds[e]), tp_r=None if np.isinf(tp) else float(tp), max_hold_s=int(H), stress=stress) for d, f in legs]
                    k, r, sd = min(res, key=lambda z: z[1])
                    tot += 1
                    if j != J[e] or k != X[e, q, h] or abs(r - R[e, q, h]) > 1e-4:
                        bad += 1
                        if bad < 5: print("MISMATCH", e, j, J[e], k, X[e, q, h], r, R[e, q, h])
        print(inst, stress, "checked", tot, "bad", bad, "both-leg seconds", both)
