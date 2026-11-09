"""quick honest event studies beyond the OI family: depth imbalance, premium dislocation, OI-change regimes.
decision points every 60 s; forward Exness mid change (in $) from s+2 to s+2+h vs round-trip cost (2 spreads)."""
import numpy as np
import pandas as pd

import lab
from lab import bc

L = lab.Lab(depth=True)
JAN = bc.ts_of("2026-01-01")
s = np.arange(JAN + 3600, bc.ts_of("2026-06-30"), 60)
T_ = L.tk["t"]
mid = 0.5 * (L.tk["bid_last"] + L.tk["ask_last"])
q = np.searchsorted(T_, s) - 1
spread = (L.tk["ask_last"] - L.tk["bid_last"])[q]
fresh = (s - T_[q]) < 10


def ex(t):
    k = np.searchsorted(T_, t, side="right") - 1
    return mid[np.clip(k, 0, len(mid) - 1)]


vol = L.vol_at(s)
D = pd.DataFrame(dict(s=s, vol=vol, spread=spread))
for h in (300, 900, 1800, 3600):
    D[f"f{h}"] = ex(s + 2 + h) - ex(s + 2)
# depth: last snapshot known (time + 5 s < s)
dp = L.depth
k = np.searchsorted(dp.ts.to_numpy() + 5, s, side="left") - 1
for lvl in ("1.0", "2.0", "5.0"):
    b = dp[f"d-{lvl}"].to_numpy()[k]
    a = dp[f"d+{lvl}"].to_numpy()[k]
    D[f"imb{lvl}"] = (b - a) / (b + a)
# premium: last known minute close; z vs past 24h
pr = L.premium
pk = np.searchsorted(pr.known_ts.to_numpy(), s, side="right") - 1
pc = pr.close.to_numpy()
pz = pd.Series(pc)
mu = pz.rolling(1440, min_periods=600).mean().to_numpy()
sd = pz.rolling(1440, min_periods=600).std().to_numpy()
D["prem_z"] = (pc[pk] - mu[pk]) / sd[pk]
# past returns (Binance) for momentum / reversal
i = s - L.t0
for w in (5, 15, 60):
    D[f"r{w}"] = L.c[i - 1] - L.c[i - 1 - 60 * w]
D["month"] = pd.to_datetime(D.s, unit="s").dt.month
D = D[fresh].dropna()
print(len(D), "median cost $", (2 * D.spread).median())


def qtab(col, h, nq=5):
    x = D.copy()
    x["q"] = pd.qcut(x[col], nq, labels=False, duplicates="drop")
    t = x.groupby(["q", "month"])[f"f{h}"].mean().unstack()
    t["all"] = x.groupby("q")[f"f{h}"].mean()
    return t.round(1)


pd.set_option("display.width", 250)
for col in ("imb1.0", "imb2.0", "imb5.0", "prem_z", "r5", "r15", "r60"):
    for h in (900, 3600):
        print(f"\n{col} -> mean forward $ move over {h}s by quintile (rows) and month")
        print(qtab(col, h).to_string())
