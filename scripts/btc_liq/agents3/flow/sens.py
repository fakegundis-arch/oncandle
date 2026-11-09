import numpy as np, pandas as pd, fast, btc_common as bc, strategy, itertools
L = fast.Lean()
base = dict(W=30, X=8, refr=900, oi_up=0.0005, big_rel=0.3, stop=10, tp=3.0, hold=7200, maxpos=2)
def run(p, a='2026-01-01', b='2026-07-01', stress=False):
    sig, d = strategy.signals(L, p, a, b); vol = L.vol[sig - L.t0]
    t = bc.trades(L, sig, d, stop_dist=p['stop'] * vol, tp_r=p['tp'], hold=p['hold'], stress=stress)
    t = t[(t.entry_ts >= bc.ts_of(a)) & (t.entry_ts < bc.ts_of(b))]
    return bc.account(t, a, b, maxpos=p['maxpos'])
print('base', {k: round(v, 3) for k, v in run(base).items()})
for k, vals in dict(W=(20, 30, 45, 60), X=(6, 7, 8, 9, 10), refr=(300, 600, 900, 1800), oi_up=(-0.0005, 0.0, 0.0005, 0.001, 0.002),
                    big_rel=(0.0, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5), stop=(8, 10, 12, 15, 20), hold=(3600, 5400, 7200, 10800), tp=(2.0, 3.0, 4.0, np.nan)).items():
    for v in vals:
        p = dict(base); p[k] = v; a = run(p); s = run(p, stress=True)
        print(f'{k}={v}: n{a["n"]} R{a["R"]:+.1f} pf{a["pf"]:.2f} ${a["final"]:.0f} dd{a["dd"]:.2f} spf{s["pf"]:.2f}')
