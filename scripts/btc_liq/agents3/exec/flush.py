"""event study: big deleveraging (OI drop over w buckets) -> Exness mid path after the row is known (fade direction)."""
import numpy as np, pandas as pd, lab
from lab import bc
L = lab.Lab()
m = L.metrics; ts = m.ts.to_numpy()
full = np.arange(ts[0], ts[-1]+1, 300)
s_oi = pd.Series(m.sum_open_interest.to_numpy(), index=ts).reindex(full)
known = full + 360; end = full + 300 - L.t0
px = lambda k: L.c[np.clip(k,0,L.n-1)]
T_ = L.tk["t"]; mid = 0.5*(L.tk["bid_last"]+L.tk["ask_last"])
def ex(t):
    k = np.searchsorted(T_, t, side="right")-1; return mid[np.clip(k,0,len(mid)-1)]
H = np.array([300, 900, 1800, 3600, 7200, 14400, 28800])
pd.set_option("display.width", 250)
for w, a, b in ((1, 0.007, 0.003), (2, 0.01, 0.004), (3, 0.01, 0.004), (3, 0.015, 0.004), (6, 0.015, 0.006)):
    doi = (s_oi/s_oi.shift(w)-1).to_numpy()
    mv = px(end)/px(end-300*w)-1
    sel = np.flatnonzero((doi <= -a) & (np.abs(mv) >= b) & (known >= bc.ts_of("2026-01-01")) & (known < bc.ts_of("2026-06-29")))
    # one event per 4 h (first)
    ev = []
    for k in sel:
        if not ev or known[k] - known[ev[-1]] >= 14400: ev.append(k)
    ev = np.array(ev)
    dec = known[ev]; d = -np.sign(mv[ev])      # fade
    vol = L.vol_at(dec)
    P = np.stack([d*(ex(dec+2+h)-ex(dec+2))/vol for h in H], 1)
    sp = (L.tk["ask_last"]-L.tk["bid_last"])[np.searchsorted(T_, dec)-1]
    df = pd.DataFrame(P, columns=[f"h{h//60}m" for h in H])
    df["month"] = pd.to_datetime(dec, unit="s").month
    df["dir"] = -d
    print(f"\nw={w} oi<=-{a} |mv|>={b}: events {len(ev)} (fade path, vol units; cost {np.median(2*sp/vol):.2f})")
    g = df.groupby("month").mean().round(1); g["n"] = df.groupby("month").size()
    print(g.to_string())
    print("all", df.mean().round(2).to_dict())
    print("down-moves (fade=buy)", df[df.dir<0].mean().round(2).to_dict(), (df.dir<0).sum())
    print("up-moves (fade=sell)", df[df.dir>0].mean().round(2).to_dict(), (df.dir>0).sum())
