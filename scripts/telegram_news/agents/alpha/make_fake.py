"""Luck check data: all posts moved by one random time shift (circular inside the post date range), text and story
structure unchanged.  Writes posts{tag}.pkl, base{tag}_*.npz, feats{tag}.pkl.  Usage: python make_fake.py SEED"""
import gc, sys
import numpy as np, pandas as pd
from lib import C, DATA, WORK, mid_last, known_price, minute_vol, lean_ticks
from prep_base import OFFS
import feats

seed = int(sys.argv[1])
tag = f"_fake{seed}"
rng = np.random.default_rng(seed)
p = pd.read_pickle(f"{WORK}/posts.pkl")
lo, hi = int(pd.Timestamp("2025-01-01", tz="UTC").timestamp()), int(pd.Timestamp("2026-07-01", tz="UTC").timestamp())
shift = int(rng.uniform(5, 60) * 86400 + rng.uniform(0, 86400))
ts = p.ts.to_numpy(np.int64)
ts2 = lo + (ts - lo + shift) % (hi - lo)
q = p.copy(); q["ts"] = ts2
q = q.sort_values(["ts", "ch", "id"]).reset_index(drop=True)
q.to_pickle(f"{WORK}/posts{tag}.pkl")
print("shift days", shift / 86400)
ts = q.ts.to_numpy(np.int64)
for inst in ["gold", "nasdaq"]:
    tk = lean_ticks(inst); T = tk["t"]; px = mid_last(tk)
    P = np.stack([known_price(T, px, ts + o) for o in OFFS], 1)
    i2 = np.searchsorted(T, ts + C.LAT); ii = np.clip(i2, 0, len(T) - 1)
    ok = (i2 < len(T)) & (T[ii] - (ts + C.LAT) <= 10)
    np.savez(f"{WORK}/base{tag}_{inst}.npz", P=P, offs=OFFS, vol60=minute_vol(T, px, ts, 60), vol15=minute_vol(T, px, ts, 15),
             vol240=minute_vol(T, px, ts, 240), spr=np.where(ok, tk["ask_first"][ii] - tk["bid_first"][ii], np.nan), ok=ok)
    C._TK.clear(); C._GAPS.clear(); del tk, T, px; gc.collect()
f = feats.build(q, C.load_calendar(DATA))
f.to_pickle(f"{WORK}/feats{tag}.pkl")
print("done", tag)
