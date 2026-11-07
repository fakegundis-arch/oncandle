"""OCO straddle outcomes: at post + LAT (+delay) place a buy stop at mid + x*vol and a sell stop at mid - x*vol
(expire E s), stop y*vol, target/timer grid.  Also single-leg variants via 'up only' / 'down only' (side=1/2)."""
import gc, sys, time
import numpy as np, pandas as pd
from lib import C, WORK, lean_ticks
from engine import gaps
from engine2 import oco_outcomes

XS = np.array([0.5, 1.0, 2.0])
ES = np.array([60, 300])
YS = np.array([1.0, 2.0, 4.0])
TPS = np.array([1.0, 2.0, 4.0, np.inf])
TIMERS = np.array([120, 600, 3600])
DELAY = 0

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    p = pd.read_pickle(f"{WORK}/posts{tag}.pkl")
    ts = p.ts.to_numpy(np.int64); n = len(ts)
    for inst in ["gold", "nasdaq"]:
        t0 = time.time()
        b = np.load(f"{WORK}/base{tag}_{inst}.npz")
        vol = np.where(np.isfinite(b["vol60"]), b["vol60"], b["vol240"])
        tk = lean_ticks(inst); T = tk["t"]; g = gaps(T)
        out = {}
        for stress in [False, True]:
            lat = C.LAT_STRESS if stress else C.LAT
            shape = (n, len(XS), len(ES), len(YS), len(TPS), len(TIMERS))
            R = np.full(shape, np.nan, np.float32); DT = np.full(shape, -1, np.int32)
            ET = np.full((n, len(XS), len(ES)), -1, np.int64); D = np.zeros((n, len(XS), len(ES)), np.int8)
            for a, x in enumerate(XS):
                for e, E in enumerate(ES):
                    for c, y in enumerate(YS):
                        off = np.where(np.isfinite(vol), x * vol, 0.0)
                        i0, r, X, J, Dd, SD = oco_outcomes(tk, g, ts + lat + DELAY, off, off, y * np.nan_to_num(vol), int(E), TPS, TIMERS, stress=stress)
                        ok = J >= 0
                        r[~ok] = np.nan
                        R[:, a, e, c] = r
                        jj = np.clip(J, 0, len(T) - 1)
                        DT[:, a, e, c] = np.where(ok[:, None, None], T[np.clip(X, 0, len(T) - 1)] - T[jj][:, None, None], -1)
                        ET[:, a, e] = np.where(ok, T[jj], -1); D[:, a, e] = Dd
            sfx = "_s" if stress else ""
            out[f"R{sfx}"] = R; out[f"DT{sfx}"] = DT; out[f"ET{sfx}"] = ET; out[f"D{sfx}"] = D
            print(inst, stress, round(time.time() - t0), flush=True)
        np.savez(f"{WORK}/oco{tag}_{inst}.npz", **out)
        del out, tk, T; gc.collect()
