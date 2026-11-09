"""honest OI-family variants at every 5-min row (known at ct+360): forward Exness mid change net of 2 spreads,
in vol units, per month.  direction = sign of the price move over the window that the OI change covers."""
import numpy as np
import pandas as pd

import lab
from lab import bc

L = lab.Lab()
m = L.metrics
ts = m.ts.to_numpy()
s_oi = pd.Series(m.sum_open_interest.to_numpy(), index=ts).reindex(np.arange(ts[0], ts[-1] + 1, 300))
e_oi = L.eth.set_index("ts").sum_open_interest.reindex(s_oi.index)
ct = s_oi.index.to_numpy()
dec = ct + 360
keep = (dec >= bc.ts_of("2026-01-01")) & (dec < bc.ts_of("2026-06-30"))
end = ct + 300 - L.t0          # bucket end index
T_ = L.tk["t"]
mid = 0.5 * (L.tk["bid_last"] + L.tk["ask_last"])
q = np.searchsorted(T_, np.clip(dec, 0, None)) - 1
spread = (L.tk["ask_last"] - L.tk["bid_last"])[np.clip(q, 0, len(T_) - 1)]


def ex(t):
    k = np.searchsorted(T_, t, side="right") - 1
    return mid[np.clip(k, 0, len(mid) - 1)]


px = lambda k: L.c[np.clip(k, 0, L.n - 1)]
vol = L.vol_at(dec)
D = pd.DataFrame(dict(dec=dec, vol=vol, cost=2 * spread / vol))
for w in (1, 2, 3, 6, 12):
    D[f"doi{w}"] = (s_oi / s_oi.shift(w) - 1).to_numpy()
    D[f"eoi{w}"] = (e_oi / e_oi.shift(w) - 1).to_numpy()
    D[f"mv{w}"] = px(end) / px(end - 300 * w) - 1
    D[f"mvv{w}"] = (px(end) - px(end - 300 * w)) / vol
for h in (300, 900, 1800, 3600, 7200):
    D[f"f{h}"] = (ex(dec + 2 + h) - ex(dec + 2)) / vol
D["month"] = pd.to_datetime(D.dec, unit="s").dt.month
D = D[keep].dropna().reset_index(drop=True)
print(len(D))
pd.set_option("display.width", 250)
res = []
for w in (1, 2, 3, 6, 12):
    d = np.sign(D[f"mv{w}"])
    for oi_rule, oim in (("oi<=-a", lambda a: D[f"doi{w}"] <= -a), ("oi>=+a", lambda a: D[f"doi{w}"] >= a),
                         ("eth<=-a", lambda a: D[f"eoi{w}"] <= -a)):
        for a in (0.002, 0.004, 0.007, 0.01):
            for mvv in (3, 6, 10, 15):
                s = oim(a) & (D[f"mvv{w}"].abs() >= mvv)
                # thin overlapping signals: one per 30 min
                idx = np.flatnonzero(s.to_numpy())
                if len(idx) == 0:
                    continue
                kept = [idx[0]]
                for k in idx[1:]:
                    if D.dec[k] - D.dec[kept[-1]] >= 1800:
                        kept.append(k)
                kept = np.array(kept)
                if len(kept) < 30:
                    continue
                for h in (900, 1800, 3600, 7200):
                    for side in (1, -1):
                        y = side * d[kept] * D[f"f{h}"].to_numpy()[kept] - D.cost.to_numpy()[kept]
                        mo = pd.Series(y).groupby(D.month.to_numpy()[kept]).mean()
                        res.append(dict(w=w, rule=oi_rule, a=a, mvv=mvv, h=h, side=side, n=len(kept), mean=y.mean(),
                                        t=y.mean() / y.std() * np.sqrt(len(y)), pos_months=(mo > 0).sum(),
                                        **{f"m{k}": v for k, v in mo.round(2).items()}))
R = pd.DataFrame(res)
R.to_parquet("oi_variants.parquet")
print("combos", len(R))
print(R.sort_values("t", ascending=False).head(30).round(2).to_string())
