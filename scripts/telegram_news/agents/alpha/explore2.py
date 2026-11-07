import numpy as np, pandas as pd
from lib import WORK
p = pd.read_pickle(f"{WORK}/posts.pkl")
low = p.clean.str.lower()
groups = {
    "all": np.ones(len(p), bool),
    "excl": p.clean.str.contains("❗").to_numpy(),
    "dblexcl": p.clean.str.contains("‼").to_numpy(),
    "macro": (p.clean.str.contains(r"\$MACRO") | p.clean.str.contains(r"Actual .*\(Forecast", regex=True)).to_numpy(),
    "trump": low.str.contains("trump").to_numpy(),
    "iran": low.str.contains("iran").to_numpy(),
    "tariff": low.str.contains("tariff").to_numpy(),
    "fed": low.str.contains(r"\bfed\b|powell|fomc").to_numpy(),
    "ceasefire": low.str.contains("ceasefire|peace|truce").to_numpy(),
    "strike": low.str.contains("strike|attack|missile|explosion").to_numpy(),
    "hormuz": low.str.contains("hormuz").to_numpy(),
    "gold": low.str.contains("gold").to_numpy(),
}
for inst in ["gold", "nasdaq"]:
    b = np.load(f"{WORK}/base_{inst}.npz")
    P, offs, v = b["P"], list(b["offs"]), b["vol60"]
    print("=====", inst)
    o = offs
    # mean abs change per second between consecutive offsets
    seg = [(o[k], o[k + 1]) for k in range(len(o) - 1) if -300 <= o[k] < 300]
    print("seg     " + " ".join(f"{a:>5d}" for a, _ in seg))
    for g, m in groups.items():
        for ch in ["FJ", "WB"]:
            mm = m & (p.ch == ch).to_numpy() & ~np.isnan(v)
            if mm.sum() < 30:
                continue
            row = []
            for a, bb in seg:
                d = np.abs(P[mm, o.index(bb)] - P[mm, o.index(a)]) / v[mm] / np.sqrt(bb - a) * np.sqrt(60)
                row.append(np.nanmean(d))
            print(f"{g:9s}{ch} n={mm.sum():5d} " + " ".join(f"{x:5.2f}" for x in row))
