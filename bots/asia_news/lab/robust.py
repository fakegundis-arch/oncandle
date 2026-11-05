"""Robustness of a candidate (Jan-Jun 2026): neighbours, leave-out, breakdowns, placebos.
usage: python robust.py '<json cfg>'
Placebos:
  clock   same rule, same clock time, weekdays without a release (time-of-day matched)
  shift   same rule on the RELEASE DAYS but at the release minute -90/-60/-30/+30/+60/+90 min (same days, other minutes)
  random  same entries / exits, random direction (5000x)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import sim as S  # noqa: E402
import strat as St  # noqa: E402

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)


def shift_placebo(P, offsets=(-90, -60, -30, 30, 60, 90)):
    ctxs, info = St.news_set()
    out = {}
    for off in offsets:
        ts = [c["t"] + pd.Timedelta(minutes=off) for c in ctxs]
        cs = S.contexts(ts, "shift")
        rows = []
        for c in cs:
            inf = dict(info[c["t"] - pd.Timedelta(minutes=off)])
            tr = St.trade_one(P, c, inf)
            if tr is not None:
                rows.append(tr)
        t = pd.DataFrame(rows)
        out[off] = (len(t), round(t.r.sum(), 2) if len(t) else 0, round(St.metrics(t)["pf"], 2) if len(t) else 0)
    return out


def random_dir(P, t, n=5000):
    """flip each trade's direction: needs re-simulation per trade (both directions)."""
    ctxs, info = St.news_set()
    by_t = {c["t"]: c for c in ctxs}
    up, dn = [], []
    for row in t.itertuples():
        c = by_t[row.t]
        es = St.entries(P, c, info.get(c["t"]))
        e = es[0]
        res = {}
        for d in (1, -1):
            ct = e["ct"]
            fill = S.O[e["i"]] + ct if d > 0 else S.O[e["i"]]
            r = S.run_trade(e["i"], fill, d, e["sd"], P.get("tp_r", 0), St._exit_tm(P, e["i"], c), ct,
                            P.get("trail", 0), P.get("be", 0), P.get("be_lock", 0))
            res[d] = r[0]
        up.append(res[1]); dn.append(res[-1])
    up, dn = np.array(up), np.array(dn)
    s = np.random.default_rng(0).integers(0, 2, (n, len(up)))
    R = (s * up + (1 - s) * dn).sum(1)
    return dict(always_long=round(up.sum(), 2), always_short=round(dn.sum(), 2), random_mean=round(R.mean(), 2),
                p_random_ge=round(float((R >= t.r.sum()).mean()), 4))


def main(P):
    o, t = St.evaluate(P)
    print("candidate:", P)
    print(o)
    print(t.to_string())
    t["month"] = t.entry_time.dt.month
    print("by ccy :", t.groupby("ccy").r.agg(["count", "sum", "mean"]).round(2).to_dict("index"))
    print("by kind:", t.groupby("kind").r.agg(["count", "sum", "mean"]).round(2).to_dict("index"))
    print("by month:", t.groupby("month").r.sum().round(2).to_dict())
    print("by dir :", t.groupby("dir").r.agg(["count", "sum"]).round(2).to_dict("index"))
    rr = np.sort(t.r.to_numpy())[::-1]
    print("R without best 1/2/3:", [round(rr[k:].sum(), 2) for k in (1, 2, 3)])
    nj = t[t.ccy != "JPY"]
    print("without JPY: n %d R %.2f PF %.2f" % (len(nj), nj.r.sum(), St.metrics(nj)["pf"]))
    print("shift placebo (n, R, PF) by offset:", shift_placebo(P))
    if P["fam"] in ("news", "mom", "fade", "always", "pairdir"):
        print("random direction:", random_dir(P, t))


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
