"""honest timing: follow / fade x market / stop / limit entries x exits, mean r per signal set (no account)."""
import itertools
import sys
import time

import numpy as np
import pandas as pd

import lab
from lab import bc
from engine import JAN, MAY, JUL

L = lab.Lab()
f = pd.read_parquet("sig_all.parquet")
f = f[(f.doi <= -0.0015) & (f.mv_abs >= 0.001)].sort_values("dec").reset_index(drop=True)
sets = {"A": ((f.doi <= -0.002) & (f.mv_abs >= 0.0015)).to_numpy(),
        "B": ((f.doi <= -0.003) & (f.mv_abs >= 0.002)).to_numpy(),
        "C": ((f.doi <= -0.005) & (f.mv_abs >= 0.003)).to_numpy(),
        "D": ((f.doi <= -0.002) & (f.mv_abs >= 0.004)).to_numpy()}
sig, d, vol = f.dec.to_numpy(), f.dir.to_numpy(), f.vol.to_numpy()
print("signals", len(f), {k: v.sum() for k, v in sets.items()})
entries = [(0, 0.0, 0)] + [(k, o, lf) for k in (1, 2) for o in (0.5, 1, 2, 3, 5) for lf in (120, 300, 900, 1800)]
grid = list(itertools.product((1, -1), entries, (2, 3, 5, 8), (120, 300, 600, 1800), (np.nan, 1.0, 2.0)))
rows = []
t = time.time()
a_mask = (sig < MAY)
for side, (kind, off, life), st, h, tp in grid:
    ent, ext, rr, sd, px = L.nbt(sig, side * d, kind, off * vol, life, st * vol, tp, h, np.nan, np.nan)
    for name, s in sets.items():
        ok = s & ~np.isnan(rr)
        A = ok & a_mask
        B = ok & ~a_mask
        rows.append(dict(set=name, side=side, kind=kind, off=off, life=life, stop=st, hold=h, tp=tp,
                         nA=A.sum(), RA=rr[A].sum(), mA=rr[A].mean() if A.any() else np.nan,
                         nB=B.sum(), RB=rr[B].sum(), mB=rr[B].mean() if B.any() else np.nan))
print("time", time.time() - t)
r = pd.DataFrame(rows)
r.to_parquet("exp1.parquet")
pd.set_option("display.width", 250)
for name in sets:
    x = r[r.set == name]
    print("\n== set", name)
    print(x.sort_values("RA", ascending=False).head(15).round(3).to_string())
    print("share of settings with RA>0: %.2f, RB>0: %.2f, both: %.2f" % ((x.RA > 0).mean(), (x.RB > 0).mean(),
                                                                       ((x.RA > 0) & (x.RB > 0)).mean()))
    # summary by side x kind
    print(x.groupby(["side", "kind"])[["mA", "mB"]].mean().round(3).to_string())
