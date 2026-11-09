"""fixed-rule luck check: the frozen candidate rule applied to its own signals moved by random 1-14 days (same
direction, stop / offset re-measured at the new time with the signal's flush size), 200 times."""
import numpy as np, pandas as pd, sys, json
import strategy, verify
from lab import bc
mk = verify.Adapter(start="2025-12-01", end="2026-07-01")
JAN, JUL = bc.ts_of("2026-01-01"), bc.ts_of("2026-07-01")
for name, p in json.loads(sys.argv[1]).items():
    for k in ("tp", "be", "tr"):
        if p.get(k) is None: p[k] = np.nan
    dec, d, vol, move = strategy.signals(mk, p)
    keep = (dec >= JAN - 7200) & (dec < JUL)
    dec, d, move = dec[keep], d[keep], move[keep]
    rel = move / mk.c[dec - mk.t0 - 1]
    out = []
    for seed in range(201):
        if seed == 0:
            new = dec
        else:
            rng = np.random.default_rng(1000 + seed)
            days = rng.integers(1, 15, len(dec)); sg = rng.choice([-1, 1], len(dec))
            new = dec + sg * days * 86400
            bad = (new < JAN + 7200) | (new >= JUL - 3600)
            new[bad] = dec[bad] - sg[bad] * days[bad] * 86400
        o = np.argsort(new, kind="stable"); s_, d_, r_ = new[o], d[o], rel[o]
        v = mk.vol[s_ - mk.t0]; mv_ = r_ * mk.c[s_ - mk.t0 - 1]
        sd = p["stop"] * (v if p.get("stype", "v") == "v" else mv_)
        t = bc.trades(mk, s_, d_, kind=p["kind"], offset=p["off"] * v, life=p["life"], stop_dist=sd, tp_r=p["tp"],
                      hold=p["hold"], be_at=p["be"], trail=p["tr"])
        a = bc.account(t, "2026-01-01", "2026-07-01", maxpos=p["maxpos"])
        out.append((a["R"], a["final"], a["n"]))
    out = np.array(out)
    real, fk = out[0], out[1:]
    print(f"{name}: real R {real[0]:.1f} ${real[1]:.0f} n {real[2]:.0f} | 200 fakes: R mean {fk[:,0].mean():.1f} sd {fk[:,0].std():.1f} "
          f"max {fk[:,0].max():.1f}  p95 {np.percentile(fk[:,0],95):.1f}  final max ${fk[:,1].max():.0f} median ${np.median(fk[:,1]):.0f}  "
          f"share fakes >= real R: {(fk[:,0] >= real[0]).mean():.3f}")
