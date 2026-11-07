"""Precompute, for every post, instrument, delay, direction and stop size, the R of market trades for a grid of
targets x timers (normal and stress), with exit times.  Uses engine.py (identical to common.py)."""
import gc, os, sys, time
import numpy as np, pandas as pd
from lib import C, DATA, WORK, lean_ticks
from engine import gaps, market_outcomes

DELAYS = np.array([0, 10, 30])
STOPS = np.array([0.75, 1.5, 3.0, 6.0])        # x vol60
TPS = np.array([0.5, 1.0, 2.0, 4.0, np.inf])
TIMERS = np.array([30, 120, 600, 3600])

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    p = pd.read_pickle(f"{WORK}/posts{tag}.pkl")
    ts = p.ts.to_numpy(np.int64)
    n = len(ts)
    for inst in ["gold", "nasdaq"]:
        t0 = time.time()
        b = np.load(f"{WORK}/base{tag}_{inst}.npz")
        vol = np.where(np.isfinite(b["vol60"]), b["vol60"], b["vol240"])
        tk = lean_ticks(inst)
        T = tk["t"]; g = gaps(T)
        nd, ns = len(DELAYS), len(STOPS)
        shape = (n, nd, 2, ns, len(TPS), len(TIMERS))
        out = {}
        for stress in [False, True]:
            lat = C.LAT_STRESS if stress else C.LAT
            R = np.full(shape, np.nan, np.float32)
            DT = np.full(shape, -1, np.int32)
            JS = np.full((n, nd), -1, np.int64)
            SD = np.full((n, nd, ns), np.nan, np.float32)
            for a, dl in enumerate(DELAYS):
                for b_, dd in enumerate([1, -1]):
                    for c, sm in enumerate(STOPS):
                        dec = ts + lat + dl
                        sds = sm * vol
                        js, r, X, sd = market_outcomes(tk, g, dec, np.full(n, dd), sds, TPS, TIMERS, stress)
                        js = np.where(np.isfinite(vol), js, -1)
                        ok = js >= 0
                        r[~ok] = np.nan
                        R[:, a, b_, c] = r
                        jj = np.clip(js, 0, len(T) - 1)
                        DT[:, a, b_, c] = np.where(ok[:, None, None], T[np.clip(X, 0, len(T) - 1)] - T[jj][:, None, None], -1)
                        JS[:, a] = js
                        SD[:, a, c] = np.where(ok, sd, np.nan)
            ET = np.where(JS >= 0, T[np.clip(JS, 0, len(T) - 1)], -1)
            sfx = "_s" if stress else ""
            out[f"R{sfx}"] = R; out[f"DT{sfx}"] = DT; out[f"ET{sfx}"] = ET; out[f"SD{sfx}"] = SD
            print(inst, "stress", stress, "done", round(time.time() - t0, 1), flush=True)
        np.savez(f"{WORK}/out{tag}_{inst}.npz", **out, delays=DELAYS, stops=STOPS, tps=TPS, timers=TIMERS)
        del out, R, DT; C._TK.clear(); C._GAPS.clear(); del tk, T; gc.collect()
