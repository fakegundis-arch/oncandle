"""Step 1b: NAS100's Asian-session behaviour on ALL weekdays of Jan-Jun 2026 (no news needed) - the background any
news rule must beat: drift, the US session's move carried into Asia (continuation / reversal), time-of-day volatility,
and the cross-asset reaction of the currency pairs at the releases (does Nasdaq follow AUDUSD / USDJPY?).
usage: python study_context.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)


def at(m, t):
    i = m.index.searchsorted(t, side="right") - 1
    return m.close.iat[i]


def main():
    m = C.px()
    days = pd.date_range("2026-01-01", "2026-06-30", freq="D")
    rows = []
    for d in days:
        if d.weekday() >= 5:
            continue
        # Asian session of day d: 23:00 (d-1) .. 07:00 d UTC; US cash session of the previous day 14:30-20:00 UTC
        a0, a1 = d - pd.Timedelta(hours=1), d + pd.Timedelta(hours=7)
        us0, us1 = d - pd.Timedelta(hours=9, minutes=30), d - pd.Timedelta(hours=4)
        if d.weekday() == 0:                      # Monday: previous US session is Friday
            us0 -= pd.Timedelta(days=2); us1 -= pd.Timedelta(days=2)
        w = m.loc[a0:a1]
        if len(w) < 300:
            continue
        atr = C.atr_h1(a0)
        r = dict(day=d, atr=atr, us=(at(m, us1) - at(m, us0)) / atr, asia=(at(m, a1) - at(m, a0)) / atr,
                 a_00_03=(at(m, d + pd.Timedelta(hours=3)) - at(m, d)) / atr,
                 a_03_07=(at(m, a1) - at(m, d + pd.Timedelta(hours=3))) / atr)
        for h0 in (0, 1, 2, 3, 4, 5, 6):
            ww = m.loc[d + pd.Timedelta(hours=h0): d + pd.Timedelta(hours=h0 + 1) - C.ONE]
            r[f"rng{h0}"] = (ww.high.max() - ww.low.min()) / atr if len(ww) else np.nan
        rows.append(r)
    D = pd.DataFrame(rows)
    print(f"weekdays: {len(D)}")
    print("Asian session 23:00-07:00 UTC move (ATR): mean %.3f median %.3f up %.0f%%" % (D.asia.mean(), D.asia.median(), 100 * (D.asia > 0).mean()))
    print("by month:", D.groupby(D.day.dt.month).asia.mean().round(2).to_dict())
    print("corr(prev US session, Asia) = %.3f; Asia signed by US sign: mean %.3f (%.0f%% same sign)" % (
        D.us.corr(D.asia), (np.sign(D.us) * D.asia).mean(), 100 * (np.sign(D.us) == np.sign(D.asia)).mean()))
    print("corr(00-03, 03-07) = %.3f" % D.a_00_03.corr(D.a_03_07))
    print("hourly range (ATR) by UTC hour:", D[[f"rng{h}" for h in range(7)]].mean().round(3).to_dict())

    # cross-asset at the releases: release-minute and 15-min moves of the pair vs NAS100
    rt = C.rel_table()
    import asia_news_lab as L
    pairs = {s: L.prices_train(s) for s in ("AUDUSD", "NZDUSD", "USDJPY")}
    out = []
    for r in rt.itertuples():
        sym, sg = L.PAIR.get(r.ccy, (None, 1))
        if sym is None:
            continue
        p = pairs[sym]
        t = r.time
        if t not in m.index:
            continue
        x = dict(t=t, ccy=r.ccy, kind=r.kind, bias=r.bias)
        for k in (1, 5, 15, 60):
            tk = t + pd.Timedelta(minutes=k)
            x[f"pair{k}"] = sg * (at(p, tk - C.ONE) - at(p, t - C.ONE)) / C.L.COST[sym]
            x[f"nq{k}"] = (at(m, tk - C.ONE) - at(m, t - C.ONE)) / C.atr_h1(t)
        out.append(x)
    X = pd.DataFrame(out)
    print("\nrelease reactions: pair (signed so + = released currency stronger, in spreads) vs NAS100 (ATR)")
    print(X.round(2).to_string(index=False))
    for k in (1, 5, 15, 60):
        print(f"corr(pair{k}, nq{k}) all = {X[f'pair{k}'].corr(X[f'nq{k}']):+.2f}; AUD/NZD only = "
              f"{X[X.ccy != 'JPY'][f'pair{k}'].corr(X[X.ccy != 'JPY'][f'nq{k}']):+.2f}")


if __name__ == "__main__":
    main()
