"""Per post and instrument: known mid price at offsets around the post, 60-min vol, spread at the decision second."""
import gc
import time

import numpy as np

from lib import C, DATA, WORK, posts, mid_last, known_price, minute_vol, lean_ticks

OFFS = np.array([-3600, -1800, -900, -600, -300, -120, -60, -30, -10, -5, 0, 1, 2, 3, 5, 7, 10, 12, 15, 20, 30, 45, 60,
                 90, 120, 180, 300, 600, 900, 1200, 1800, 3600])

if __name__ == "__main__":
    p = posts()
    p[["ts", "ch", "id", "clean"]].to_pickle(f"{WORK}/posts.pkl")
    ts = p.ts.to_numpy(np.int64)
    for inst in ["gold", "nasdaq"]:
        t0 = time.time()
        tk = lean_ticks(inst)
        T = tk["t"]
        px = mid_last(tk)
        P = np.stack([known_price(T, px, ts + o) for o in OFFS], 1).astype(np.float64)
        vol60 = minute_vol(T, px, ts, 60)
        vol15 = minute_vol(T, px, ts, 15)
        vol240 = minute_vol(T, px, ts, 240)
        i2 = np.searchsorted(T, ts + C.LAT)
        ok = (i2 < len(T)) & (T[np.clip(i2, 0, len(T) - 1)] - (ts + C.LAT) <= 10)
        ii = np.clip(i2, 0, len(T) - 1)
        spr = np.where(ok, tk["ask_first"][ii] - tk["bid_first"][ii], np.nan)
        np.savez(f"{WORK}/base_{inst}.npz", P=P, offs=OFFS, vol60=vol60, vol15=vol15, vol240=vol240, spr=spr, ok=ok)
        print(inst, "done", time.time() - t0, np.isnan(P).mean(0).round(3))
        C._TK.clear(); C._GAPS.clear(); del tk, T, px; gc.collect()
