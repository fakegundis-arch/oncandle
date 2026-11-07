import sys, numpy as np
from wf_analyze import load, describe
for name in sys.argv[1:]:
    res, meta, fn, rn, nc = load(name)
    seg = [res[:, 0]] + [res[:, b] - res[:, b - 1] for b in range(1, 4)]   # A=2025, B=Jan-Feb, C=Mar-Apr, D=May-Jun
    n = np.stack([s[:, 0] for s in seg], 1); R2 = np.stack([s[:, 10] for s in seg], 1); R = np.stack([s[:, 1] for s in seg], 1)
    lg = np.stack([s[:, 5] for s in seg], 1)
    for nmin in [5, 10, 20]:
        ok = (n >= nmin).all(1)
        allpos = ok & (R2 > 0).all(1)
        abc = ok & (R2[:, :3] > 0).all(1)
        print(f"{name}: n>={nmin} each seg: {ok.sum():7d}  stressR>0 in A,B,C: {abc.sum():6d}  ... and D too: {allpos.sum():5d}  frac D>0 given ABC: {allpos.sum()/max(abc.sum(),1):.2f}  (uncond D>0: {(ok & (R2[:,3]>0)).sum()/max(ok.sum(),1):.2f})")
    ok = (n >= 10).all(1) & (R2[:, :3] > 0).all(1)
    idx = np.flatnonzero(ok)
    idx = idx[np.argsort(-lg[idx, :3].sum(1))][:15]
    for i in idx:
        print("   ", describe(meta, fn, rn, i), "| R by seg", R[i].round(1), "| stress", R2[i].round(1), "| n", n[i].astype(int))
