import numpy as np, pandas as pd
from lib import WORK
p = pd.read_pickle(f"{WORK}/posts.pkl")
low = p.clean.str.lower()
cat = {
    "all": np.ones(len(p), bool),
    "excl": p.clean.str.contains("❗").to_numpy(),
    "brk": p.clean.str.contains("‼|BREAKING|🚨|⚠", regex=True).to_numpy(),
    "siren": p.clean.str.contains("🚨").to_numpy(),
    "macro": (p.clean.str.contains(r"\$MACRO") | p.clean.str.contains(r"(?i)actual .*\(forecast", regex=True)).to_numpy(),
    "trump": low.str.contains("trump").to_numpy(),
    "iran": low.str.contains("iran|hormuz|tehran").to_numpy(),
    "tariff": low.str.contains("tariff").to_numpy(),
    "fed": low.str.contains(r"\bfed\b|powell|fomc|warsh").to_numpy(),
}
ts = p.ts.to_numpy()
search = ts < pd.Timestamp("2026-05-01", tz="UTC").timestamp()
for inst in ["gold", "nasdaq"]:
    b = np.load(f"{WORK}/base_{inst}.npz")
    P, offs, v = b["P"], list(b["offs"]), b["vol60"]
    c = lambda o: P[:, offs.index(o)]
    print("=====", inst)
    for (a, bb) in [(-60, 2), (-10, 2), (0, 2), (0, 10), (0, 30), (2, 30), (0, 60)]:
        pre = (c(bb) - c(a)) / v
        for H in [60, 300, 900]:
            if bb + H not in offs:
                continue
            f = (c(bb + H) - c(bb)) / v
            line = [f"pre[{a},{bb}] H={H}"]
            for g, m in cat.items():
                for th in [1.0, 2.5]:
                    s = m & ~np.isnan(pre) & ~np.isnan(f) & (np.abs(pre) > th)
                    x = np.sign(pre[s]) * f[s]
                    if len(x) < 20:
                        line.append(f"{g}>{th}:  -   ")
                        continue
                    tt = x.mean() / (x.std() / np.sqrt(len(x)))
                    line.append(f"{g}>{th}:{len(x)}:{x.mean():+.2f}({tt:+.1f})")
            print(" ".join(line))
