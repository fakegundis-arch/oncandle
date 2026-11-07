import numpy as np, time
from lib import C, DATA, WORK
import pandas as pd
from engine import gaps, market_outcomes

p = pd.read_pickle(f"{WORK}/posts.pkl")
rng = np.random.default_rng(0)
tps = np.array([0.5, 1.0, 2.0, 4.0, np.inf]); timers = np.array([30, 120, 600, 3600])
for inst in ["gold", "nasdaq"]:
    tk = C.load_ticks(inst, DATA)
    g = gaps(tk["t"])
    sel = rng.choice(len(p), 300, replace=False)
    for stress in [False, True]:
        lat = C.LAT_STRESS if stress else C.LAT
        dec = p.ts.to_numpy()[sel] + lat + rng.integers(0, 30, len(sel))
        ds = rng.choice([-1, 1], len(sel))
        sds = rng.uniform(0.1, 8, len(sel)) * (1 if inst == "gold" else 8)
        t0 = time.time()
        js, R, X, SD = market_outcomes(tk, g, dec, ds, sds, tps, timers, stress)
        t1 = time.time()
        bad = 0; tot = 0
        for e in range(len(sel)):
            m = C.market_entry(tk, int(dec[e] - lat), int(ds[e]), delay=0, stress=stress)
            if m is None:
                assert js[e] < 0; continue
            i, fill = m
            assert i == js[e]
            for q, tp in enumerate(tps):
                for h, H in enumerate(timers):
                    k, r, sd = C.exit_trade(tk, i, fill, int(ds[e]), float(sds[e]), tp_r=None if np.isinf(tp) else float(tp), max_hold_s=int(H), stress=stress)
                    tot += 1
                    if k != X[e, q, h] or abs(r - R[e, q, h]) > 1e-4 or abs(sd - SD[e]) > 1e-9:
                        bad += 1
                        if bad < 5: print("MISMATCH", inst, e, q, h, k, X[e, q, h], r, R[e, q, h], sd, SD[e])
        print(inst, "stress", stress, "checked", tot, "mismatches", bad, "numba s", round(t1 - t0, 2))
    C._TK.clear(); C._GAPS.clear()
