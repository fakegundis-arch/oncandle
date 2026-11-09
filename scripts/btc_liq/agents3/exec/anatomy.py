import numpy as np
import pandas as pd

import lab
from lab import bc

L = lab.Lab()
f = pd.read_parquet("sig.parquet")
f = f[(f.dec >= bc.ts_of("2026-01-01")) & (f.dec < bc.ts_of("2026-07-01"))].reset_index(drop=True)
T_ = L.tk["t"]
mid = 0.5 * (L.tk["bid_last"] + L.tk["ask_last"])
ks = np.array([-60, -30, 0, 10, 30, 60, 90, 120, 180, 240, 300, 450, 600, 900, 1200, 1800, 2700, 3600])


def path(ts0):
    q = np.searchsorted(T_, ts0[:, None] + ks[None, :], side="right") - 1
    return mid[np.clip(q, 0, len(mid) - 1)]


ent = f.dec.to_numpy() + 2
P = path(ent)
p0 = P[:, ks == 0][:, 0]
rel = f.dir.to_numpy()[:, None] * (P - p0[:, None]) / f.vol.to_numpy()[:, None]
cols = [str(k) for k in ks]
R = pd.DataFrame(rel, columns=cols)
groups = {
    "all": np.ones(len(f), bool),
    "v1": (f.doi <= -0.007) & (f.mv_abs >= 0.003),
    "v2": (f.doi <= -0.005) & (f.mv_abs >= 0.003) & (f.net > 0),
    "oi3mv3": (f.doi <= -0.003) & (f.mv_abs >= 0.003),
    "oi5mv2": (f.doi <= -0.005) & (f.mv_abs >= 0.002),
    "oi3mv2net": (f.doi <= -0.003) & (f.mv_abs >= 0.002) & (f.net > 0),
    "v2_netneg": (f.doi <= -0.005) & (f.mv_abs >= 0.003) & (f.net <= 0),
}
pd.set_option("display.width", 250)
print("mean directional mid move from entry (vol units); spread ~ %.2f vol" % (f.spread / f.vol).median())
out = []
for g, s in groups.items():
    s = np.asarray(s)
    row = R[s].mean().round(2)
    row["n"] = s.sum()
    out.append(row.rename(g))
print(pd.DataFrame(out).to_string())
print("\nmedian")
out = []
for g, s in groups.items():
    s = np.asarray(s)
    row = R[s].median().round(2)
    row["n"] = s.sum()
    out.append(row.rename(g))
print(pd.DataFrame(out).to_string())
# t-stat of mean at a few horizons for v2
s = np.asarray(groups["v2"])
for k in ["60", "120", "300", "600", "1800"]:
    x = R[s][k]
    print(k, "v2 mean %.2f  t %.2f" % (x.mean(), x.mean() / x.std() * np.sqrt(len(x))))
# by month for v2 at 120/300
f["m"] = pd.to_datetime(f.dec, unit="s").dt.month
print(R[s].groupby(f.m[s]).mean()[["30", "60", "120", "300", "600"]].round(2))
