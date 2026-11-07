import numpy as np, pandas as pd, sys
from lib import WORK
p = pd.read_pickle(f"{WORK}/posts.pkl")
inst = sys.argv[1]; H = int(sys.argv[2]); N = int(sys.argv[3])
b = np.load(f"{WORK}/base_{inst}.npz")
P, offs, v = b["P"], list(b["offs"]), b["vol60"]
c = lambda o: P[:, offs.index(o)]
f = (c(H) - c(2)) / v
pre = (c(2) - c(-60)) / v
p["f"] = f; p["pre"] = pre
# one row per second-cluster: keep first post within 60s window having largest |f|
p["t"] = pd.to_datetime(p.ts, unit="s")
q = p.dropna(subset=["f"]).copy()
q["cl"] = (q.ts // 120)
q = q.loc[q.groupby("cl").f.apply(lambda s: s.abs().idxmax())]
q = q.reindex(q.f.abs().sort_values(ascending=False).index).head(N)
for _, r in q.iterrows():
    print(r.t, r.ch, f"f={r.f:+6.1f} pre={r.pre:+6.1f}", repr(r.clean[:150]))
