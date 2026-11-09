"""control: the same flush-fade execution on big 15-min moves WITHOUT a big open-interest drop."""
import numpy as np, pandas as pd
import strategy, verify
from lab import bc
mk = verify.Adapter(start="2025-12-01", end="2026-07-01")
m = mk.metrics; ts = m.ts.to_numpy(np.int64)
full = np.arange(ts[0], ts[-1]+1, 300, dtype=np.int64)
oi = pd.Series(m.sum_open_interest.to_numpy(float), index=ts).reindex(full)
known = full + 360
for w, mvth in ((3, 0.004), (3, 0.006)):
    doi = (oi/oi.shift(w)-1).to_numpy()
    end = full + 300 - mk.t0
    e = np.clip(end, 300*w, mk.n-1)
    mv = mk.c[e]/mk.c[e-300*w]-1
    ok = ~np.isnan(doi) & (known - mk.t0 < mk.n) & (end - 300*w >= 0)
    for lo, hi, name in ((-1, -0.01, "OI drop >=1% (candidate)"), (-0.01, -0.003, "OI drop 0.3-1%"), (-0.003, 0.003, "OI flat +-0.3%"), (0.003, 1, "OI rise >=0.3%")):
        sel = ok & (doi > lo) & (doi <= hi) & (np.abs(mv) >= mvth)
        dec = known[sel]; d = -np.sign(mv[sel]).astype(np.int64)
        vol = mk.vol[dec-mk.t0]; move = np.abs(mv[sel])*mk.c[dec-mk.t0-1]
        g = ~np.isnan(vol); dec, d, vol, move = dec[g], d[g], vol[g], move[g]
        t = bc.trades(mk, dec, d, kind=1, offset=4.0*vol, life=1200, stop_dist=0.75*move, tp_r=4.0, hold=14400)
        t = t.sort_values(["entry_ts","sig_ts"])
        for a, b in (("2026-01-01","2026-05-01"), ("2026-05-01","2026-07-01"), ("2026-01-01","2026-07-01")):
            x = t[(t.entry_ts>=bc.ts_of(a))&(t.entry_ts<bc.ts_of(b))]
            s = bc.account(x, a, b, maxpos=3)
            print(f"w{w} mv>={mvth} {name:26s} {a}..{b}: signals {len(dec)} n {s['n']} R {s['R']:.1f} pf {s['pf']:.2f} final {s['final']:.0f} dd {s['dd']:.2f} meanR {x.r.mean():.3f}")
