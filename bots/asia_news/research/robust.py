"""Robustness of a candidate rule set on Jan-Jun 2026: breakdowns, leave-out, signal variants, placebo, trend control."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import harness as H  # noqa: E402
from harness import L, evaluate, evaluate_pair, loo, pair_cfgs, trades  # noqa: E402
from newsbot.backtest import simulate  # noqa: E402
from newsbot.events import releases_from_frame  # noqa: E402
from newsbot.strategy import full_cfg, make_plan  # noqa: E402

pd.set_option("display.width", 250)
TB = ["unemployment rate", "cpi y/y", "cpi q/q"]
BASE = dict(signal={"vote": "ff", "tiebreak": TB}, entry_delay=15, stop_k=1.5, target_r=0, hold_min=360)
VERS = {"gold": dict(instrument="gold", symbol="XAUUSD"), "nasdaq": dict(instrument="nasdaq", symbol="NAS100"),
        "pair": dict(instrument="pair")}


def ev(name, cfg):
    return evaluate_pair(cfg) if name == "pair" else evaluate(cfg)


def detail(name, cfg):
    if name == "pair":
        return pd.concat([trades(c, detail=True) for c in pair_cfgs(cfg).values()]).sort_values("entry_time")
    return trades(cfg, detail=True)


def placebo(name, cfg, n=5000, seed=0):
    """Same events, same exits, random directions: how often is R >= the news-direction R?"""
    rels = releases_from_frame(H.CAL)
    cs = pair_cfgs(cfg) if name == "pair" else {cfg["symbol"]: cfg}
    out = {+1: [], -1: [], "news": []}
    for sym, c in cs.items():
        c = full_cfg(c); m = H.px(sym)
        for rel in rels:
            p = make_plan(rel, c, m)
            if p is None:
                continue
            res = {}
            for d in (+1, -1):
                p.direction = d
                s = simulate(m, p, L.COST[sym], c["news_mult"], c["news_window"])
                res[d] = None if s is None else s[2]
            if res[1] is None:
                continue
            out[+1].append(res[1]); out[-1].append(res[-1])
            out["news"].append(res[make_plan(rel, c, m).direction])
    up, dn, news = map(np.array, (out[+1], out[-1], out["news"]))
    rng = np.random.default_rng(seed)
    s = rng.integers(0, 2, (n, len(up)))
    R = (s * up + (1 - s) * dn).sum(1)
    return dict(n=len(up), news_R=round(news.sum(), 2), always_long_R=round(up.sum(), 2),
                always_short_R=round(dn.sum(), 2), random_mean=round(R.mean(), 2),
                p_random_ge_news=round(float((R >= news.sum()).mean()), 3))


if __name__ == "__main__":
    for name, v in VERS.items():
        cfg = {**BASE, **v}
        o, t = ev(name, cfg)
        print(f"\n######## {name}: {o}  {loo(t)}")
        d = detail(name, cfg)
        d["month"] = d.entry_time.dt.month
        print("by currency:", d.groupby("ccy").r.agg(["count", "sum", "mean"]).round(2).to_dict("index"))
        print("by kind    :", d.groupby("kind").r.agg(["count", "sum", "mean"]).round(2).to_dict("index"))
        print("by month   :", d.groupby("month").r.sum().round(2).to_dict())
        print("by dir     :", d.groupby("dir").r.agg(["count", "sum"]).round(2).to_dict("index"))
        for lab, sig in [("ff only (no tie-break)", {"vote": "ff"}), ("calc vote + tie-break", {"vote": "calc", "tiebreak": TB}),
                         ("ff + tie-break + inline->previous", {"vote": "ff", "tiebreak": TB, "inline": "previous"})]:
            print(f"  variant {lab:36s}", ev(name, {**cfg, "signal": sig})[0])
        print("  placebo:", placebo(name, cfg))
