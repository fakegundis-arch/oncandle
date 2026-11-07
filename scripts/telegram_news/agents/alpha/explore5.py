import numpy as np, pandas as pd, sys
from collections import defaultdict
from lib import WORK, tokens
p = pd.read_pickle(f"{WORK}/posts.pkl")
H = int(sys.argv[1]) if len(sys.argv) > 1 else 300
ts = p.ts.to_numpy()
t1 = pd.Timestamp("2026-01-01", tz="UTC").timestamp(); t2 = pd.Timestamp("2026-05-01", tz="UTC").timestamp()
per = np.where(ts < t1, 0, np.where(ts < t2, 1, 2))
toks = [set(tokens(x)) | ({"__excl"} if "❗" in x else set()) | ({"__siren"} if "🚨" in x else set()) for x in p.clean]
# bigrams too
for i, x in enumerate(p.clean):
    tl = tokens(x)
    toks[i] |= {a + "_" + b for a, b in zip(tl, tl[1:])}
fs = {}
for inst in ["gold", "nasdaq"]:
    b = np.load(f"{WORK}/base_{inst}.npz")
    P, offs, v = b["P"], list(b["offs"]), b["vol60"]
    f = (P[:, offs.index(H)] - P[:, offs.index(2)]) / v
    f = np.clip(f, -10, 10)
    fs[inst] = f
idx = defaultdict(list)
for i, s in enumerate(toks):
    for w in s:
        idx[w].append(i)
rows = []
for w, ii in idx.items():
    if len(ii) < 60:
        continue
    ii = np.array(ii)
    r = {"tok": w, "n": len(ii)}
    for inst, f in fs.items():
        for k in range(3):
            jj = ii[(per[ii] == k) & ~np.isnan(f[ii])]
            x = f[jj]
            r[f"{inst[0]}{k}"] = x.mean() if len(x) >= 15 else np.nan
            r[f"{inst[0]}{k}n"] = len(x)
        jj = ii[(per[ii] < 2) & ~np.isnan(f[ii])]
        x = f[jj]
        r[f"{inst[0]}t"] = x.mean() / (x.std() / np.sqrt(len(x)) + 1e-9) if len(x) > 20 else np.nan
    rows.append(r)
d = pd.DataFrame(rows)
pd.set_option("display.width", 250)
for inst in ["g", "n"]:
    dd = d.dropna(subset=[f"{inst}0", f"{inst}1"])
    dd = dd[(dd[f"{inst}0n"] >= 30) & (dd[f"{inst}1n"] >= 30)]
    cons = dd[np.sign(dd[f"{inst}0"]) == np.sign(dd[f"{inst}1"])]
    print(inst, "tokens", len(dd), "same sign in 2025 vs 2026H1:", len(cons) / len(dd))
    print("corr of token means 2025 vs Jan-Apr26:", np.corrcoef(dd[f"{inst}0"], dd[f"{inst}1"])[0, 1],
          " Jan-Apr26 vs May-Jun26:", dd[[f"{inst}1", f"{inst}2"]].dropna().corr().iloc[0, 1])
    top = dd.reindex(dd[f"{inst}t"].abs().sort_values(ascending=False).index).head(40)
    print(top[["tok", "n", f"{inst}0", f"{inst}0n", f"{inst}1", f"{inst}1n", f"{inst}2", f"{inst}2n", f"{inst}t"]].round(2).to_string())
