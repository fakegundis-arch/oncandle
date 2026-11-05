"""Idea 7: context filters (Nasdaq's trend into the release, volatility regime, day of week) on the leading entries,
and a context-only rule (fade the previous US cash session) at the releases vs the placebo times.
usage: python study_filters.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import sim as S  # noqa: E402
import strat as St  # noqa: E402
from sim import Cl, TI  # noqa: E402

pd.set_option("display.width", 250)


def close_before(tm):
    i = int(np.searchsorted(TI, tm)) - 1
    return Cl[i]


def context(ctx):
    t = ctx["t"]
    d = (t + pd.Timedelta(hours=2)).normalize()          # the Asian trading day (22:45 releases belong to the next day)
    prev = d - pd.Timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= pd.Timedelta(days=1)
    us0, us1 = prev + pd.Timedelta(hours=14, minutes=30), prev + pd.Timedelta(hours=20)
    a = ctx["atr"]
    us = (close_before(S.tmin(us1)) - close_before(S.tmin(us0))) / a
    pre6 = (ctx["pre"] - close_before(ctx["tm"] - 360)) / a
    return dict(us=us, pre6=pre6, dow=t.weekday())


def with_ctx(trades, ctxs):
    by = {c["t"]: c for c in ctxs}
    rows = []
    for r in trades.itertuples():
        x = context(by[r.t])
        rows.append(dict(r._asdict(), **x))
    return pd.DataFrame(rows)


def main():
    ctxs, info = St.news_set()
    # ATR regime: ATR at the release vs the median ATR of all releases
    med_atr = np.median([c["atr"] for c in ctxs])
    cands = {
        "final pair-reaction (AUD/NZD, N=2, stop 2, 6 h)": dict(fam="pairdir", ccys=("AUD", "NZD"), N=2, k=0.0, stop_k=2.0, tp_r=0, hold=360),
        "Nasdaq release-minute momentum (N=1, stop 1, 4 h)": dict(fam="mom", N=1, k=0.0, stop_k=1.0, tp_r=0, hold=240),
        "news sign +3 min (stop 2, 6 h)": dict(fam="news", delay=3, stop_k=2.0, tp_r=0, hold=360),
    }
    for name, P in cands.items():
        t = St.run_news(P)
        X = with_ctx(t, ctxs)
        X["atr_hi"] = [next(c["atr"] for c in ctxs if c["t"] == tt) > med_atr for tt in X.t]
        X["with_us"] = np.sign(X.us) == X.dir
        X["with_pre6"] = np.sign(X.pre6) == X.dir
        print(f"\n{name}: n {len(X)} R {X.r.sum():.2f}")
        for col in ("with_us", "with_pre6", "atr_hi"):
            g = X.groupby(col).r.agg(["count", "sum", "mean"]).round(2)
            print(f"  {col:10s}", g.to_dict("index"))
        print("  day of week", X.groupby("dow").r.agg(["count", "sum"]).round(2).to_dict("index"))
    # context-only rule: fade the previous US cash session, entered 2 min after the release (stop 2 ATR, 6 h)
    for lab, cs in (("releases", [c for c in ctxs]), ("placebo", St.placebo_set())):
        rs = []
        for c in cs:
            x = context(c)
            d = -int(np.sign(x["us"]))
            if d == 0:
                continue
            e = St._market(dict(), c, S.i_at(c["tm"] + 2), d, 2.0 * c["atr"], 1.0, c["tm"] + 2)
            if e is None:
                continue
            res = S.run_trade(e["i"], e["fill"], d, e["sd"], 0, int(TI[e["i"]]) + 360, e["ct"])
            rs.append(res[0])
        rs = np.array(rs)
        print(f"\nfade the previous US session at the {lab}: n {len(rs)} R {rs.sum():.2f} avgR {rs.mean():+.3f} "
              f"PF {rs[rs > 0].sum() / -rs[rs < 0].sum():.2f}")


if __name__ == "__main__":
    main()
