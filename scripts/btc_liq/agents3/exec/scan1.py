"""first look: market entry, exit grid, a few signal sets"""
import itertools
import time

import numpy as np
import pandas as pd

import lab
from engine import JAN, MAY, JUL, APR, acct_mask, stats

L = lab.Lab()
f = pd.read_parquet("sig.parquet")
f = f.sort_values("dec").reset_index(drop=True)
sig, d, vol = f.dec.to_numpy(), f.dir.to_numpy(), f.vol.to_numpy()
N = len(f)
stops = [2, 3, 4, 5, 6, 8, 10]
holds = [120, 180, 240, 300, 450, 600, 900]
tps = [np.nan, 1.0, 1.5, 2.0, 3.0]
bts = [(np.nan, np.nan), (1.0, np.nan), (1.0, 1.0)]
settings = list(itertools.product(stops, holds, tps, bts))
t = time.time()
S = len(settings)
ENT = np.zeros((S, N), np.int64); EXT = np.zeros((S, N), np.int64); RR = np.zeros((S, N)); SD = np.zeros((S, N)); PX = np.zeros((S, N))
for k, (st, h, tp, (be, tr)) in enumerate(settings):
    ENT[k], EXT[k], RR[k], SD[k], PX[k] = L.nbt(sig, d, 0, 0.0, 0, st * vol, tp, h, be, tr)
print("outcomes", time.time() - t)
np.savez("scan1.npz", ENT=ENT, EXT=EXT, RR=RR, SD=SD, PX=PX, settings=np.array([(a, b, c, e[0], e[1]) for a, b, c, e in settings]))

sets = {
    "v2": (f.doi <= -0.005) & (f.mv_abs >= 0.003) & (f.net > 0),
    "v1": (f.doi <= -0.007) & (f.mv_abs >= 0.003),
    "oi5mv3": (f.doi <= -0.005) & (f.mv_abs >= 0.003),
    "oi4mv25n": (f.doi <= -0.004) & (f.mv_abs >= 0.0025) & (f.net > 0),
    "oi3mv3n": (f.doi <= -0.003) & (f.mv_abs >= 0.003) & (f.net > 0),
    "oi3mv2n": (f.doi <= -0.003) & (f.mv_abs >= 0.002) & (f.net > 0),
    "oi2mv15n": (f.doi <= -0.002) & (f.mv_abs >= 0.0015) & (f.net > 0),
    "oi2mv15": (f.doi <= -0.002) & (f.mv_abs >= 0.0015),
}
rows = []
for name, s in sets.items():
    s = s.to_numpy()
    for k, setg in enumerate(settings):
        for mp in (1, 3):
            a = stats(ENT[k], EXT[k], RR[k], SD[k], PX[k], s, mp, JAN, MAY)
            b = stats(ENT[k], EXT[k], RR[k], SD[k], PX[k], s, mp, MAY, JUL)
            c = stats(ENT[k], EXT[k], RR[k], SD[k], PX[k], s, mp, JAN, JUL)
            rows.append(dict(set=name, stop=setg[0], hold=setg[1], tp=setg[2], be=setg[3][0], tr=setg[3][1], mp=mp,
                             nA=a["n"], RA=a["R"], fA=a["final"], nB=b["n"], RB=b["R"], fB=b["final"], n=c["n"], R=c["R"],
                             pf=c["pf"], final=c["final"], dd=c["dd"]))
res = pd.DataFrame(rows)
res.to_parquet("scan1_res.parquet")
pd.set_option("display.width", 250)
for name in sets:
    r = res[res.set == name]
    print("\n==", name, "best by Jan-Apr final")
    print(r.sort_values("fA", ascending=False).head(8).round(2).to_string())
    print("median final Jan-Jun over grid: mp1 %.0f  mp3 %.0f" % (r[r.mp == 1].final.median(), r[r.mp == 3].final.median()))
