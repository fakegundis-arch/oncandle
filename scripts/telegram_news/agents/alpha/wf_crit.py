import sys, numpy as np
from wf_analyze import load, stats, diff, describe
def crit_scores(res, b, kind):
    s = stats(res, b)
    if kind == "tstat100":
        ok = (s["n"] >= 100) & (s["pf2"] > 1.0) & (s["fm"] >= 0.5); sc = s["R"] / np.sqrt(np.maximum(s["n"], 1))
    elif kind == "broad200":
        ok = (s["n"] >= 200) & (s["pf2"] > 1.0); sc = s["lg"]
    elif kind == "stressR":
        ok = (s["n"] >= 60) & (s["fm"] >= 0.6); sc = s["R2"]
    elif kind == "pf2":
        ok = (s["n"] >= 60) & (s["fm"] >= 0.6); sc = s["pf2"]
    return np.where(ok, sc, -np.inf), ok
for name in sys.argv[1:]:
    res, meta, fn, rn, nc = load(name)
    print("=====", name)
    for kind in ["tstat100", "broad200", "stressR", "pf2"]:
        tot = {1: 0, 10: 0, 100: 0}; parts = []
        for f in range(3):
            sc, ok = crit_scores(res, f, kind); order = np.argsort(-sc); te = diff(res, f, f + 1)
            for k in tot:
                sel = order[:k]; sel = sel[ok[sel]]
                if len(sel): tot[k] += np.mean(te["lg"][sel])
            parts.append(f"f{f}: top10 R {np.mean(te['R'][order[:10]]):+.1f} pf2 {np.median(te['pf2'][order[:10]]):.2f}")
            if f == 2: best = describe(meta, fn, rn, order[0])
        print(f"  {kind:9s} chained $ multiple top1 x{np.exp(tot[1]):.2f} top10 x{np.exp(tot[10]):.2f} top100 x{np.exp(tot[100]):.2f} | " + " | ".join(parts))
        print("      latest pick:", best)
