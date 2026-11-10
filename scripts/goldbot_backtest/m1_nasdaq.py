"""USTECm for the days the Exness tick archive does not have yet (Nov 9 - 10 2026), from the user's own MT5 export of
1-minute bars (bid OHLC + spread in points, server time = UTC; checked against the tick archive on Oct 1 - Nov 8:
same clock, 79 % of OHLC values equal to the cent).

  1. every USTECm trade the live bot opened on Nov 9 - 10: run from its real fill price with its real SL / TP;
  2. the backtest's USTECm straddles that waited for these prices (trades_live_ai_real_to_2026-11-10.csv, "no Nasdaq
     price data yet", not vetoed by the AI review): stop prices from the live log when the live bot armed the same
     post within 10 s (exact broker quotes; and when the bars cannot tell whether a stop was touched inside the 120-s
     window, the live fill / no fill of those same orders), else the previous minute's close +/- the offset.

With minute bars the order of prices inside one minute is unknown: a result is marked "unclear" only when the
candidates inside a minute would give different outcomes.  Companion rule kept: one USTECm straddle at a time.

usage: python3 -I scripts/goldbot_backtest/m1_nasdaq.py <USTECm M1 export.csv> <newsbot.log>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_log  # noqa: E402

ROOT = HERE.parents[1]
OUT = ROOT / "results" / "goldbot_backtest"
OFFSET, SL, TP, LOT, WINDOW = 30.0, 40.0, 40.0, 0.5, 120       # config.yaml companion (today)


def load_m1(path):
    m = pd.read_csv(path, sep="\t")
    m.columns = [c.strip("<>").lower() for c in m.columns]
    m["ts"] = pd.to_datetime(m.date + " " + m.time, format="%Y.%m.%d %H:%M:%S")
    m = m.set_index("ts")
    m["sp"] = m.spread * 0.01
    return m


def touches(side, sl, tp, b):
    """(SL touched, TP touched) in bar b for an open position; SELL closes on the ask = bid + spread."""
    if side == "BUY":
        return b.low <= sl, b.high >= tp
    return b.high + b.sp >= sl, b.low + b.sp <= tp


def exit_from(m, side, fill_min, sl, tp):
    """First exit after a fill in minute fill_min.  Returns (minute, 'take profit' | 'stop loss' | ..., sure)."""
    s0, t0 = touches(side, sl, tp, m.loc[fill_min])
    for ts, b in m.loc[fill_min + pd.Timedelta(minutes=1):].iterrows():
        s, t = touches(side, sl, tp, b)
        if s or t:
            later = "both in one minute" if (s and t) else ("take profit" if t else "stop loss")
            break
    else:
        ts, later = None, "open at end of data"
    first = {(True, False): "stop loss", (False, True): "take profit", (True, True): "both in one minute"}.get((s0, t0))
    if first is None:                                   # nothing inside the fill minute: the later result stands
        return ts, later, later in ("take profit", "stop loss")
    if first == later:                                  # same answer whether the fill-minute touch came first or not
        return fill_min, first, True
    return fill_min, f"{first} in fill minute, else {later}", False


def fill_side(m, arm, end, buy, sell):
    """Which stop the window [arm, end] hits.  The arm minute also holds prices from before arming -> 'unclear'."""
    sure = True
    for ts, b in m.loc[arm.floor("min"):end.floor("min")].iterrows():
        bh, sh = b.high + b.sp >= buy, b.low <= sell
        if bh or sh:
            if ts == arm.floor("min") or ts == end.floor("min"):
                sure = False
            if bh and sh:
                return ts, "both", False
            return ts, "BUY" if bh else "SELL", sure
    return None, "", True


def main():
    m1_path, log = sys.argv[1], sys.argv[2]
    m = load_m1(m1_path)
    S = live_log.straddles(log)
    N = S[S.symbol == "USTECm"]

    # 1. the live bot's own USTECm trades on the days without tick data
    rows = []
    for s in N[(N.n_fills > 0) & (N.fill_utc >= "2026-11-09")].itertuples():
        fm = (s.fill_utc - pd.Timedelta(seconds=3)).floor("min")   # the real fill is 0-5 s before the logged line
        ts, why, sure = exit_from(m, s.side, fm, s.sl, s.tp)
        usd = {"take profit": 40.0, "stop loss": -40.0}.get(why, np.nan) * s.lots
        rows.append(dict(fill_utc=s.fill_utc, side=s.side, fill=s.fill, lots=s.lots, sl=s.sl, tp=s.tp,
                         exit_minute=ts, result=why, sure=sure, usd=usd, title=s.title))
    L = pd.DataFrame(rows)
    L.to_csv(OUT / "live_log_check" / "nasdaq_live_trades_nov9_10_m1.csv", index=False)
    print(L.drop(columns="title").to_string(index=False))

    # 2. the backtest's USTECm straddles that waited for prices
    t = pd.read_csv(OUT / "trades_live_ai_real_to_2026-11-10.csv")
    w = t[(t.symbol == "USTECm") & (t.exit_reason == "no Nasdaq price data yet") & ~t.ai_veto].copy()
    w["arm"] = pd.to_datetime(w.armed_ts, unit="s")
    open_until = pd.Timestamp("2000-01-01")
    out = []
    for r in w.sort_values("armed_ts").itertuples():
        base = dict(armed=r.arm, channel=r.channel, post_id=r.post_id, text=r.text)
        if r.arm < open_until:
            out.append(dict(base, result="skipped: previous USTECm straddle still open", usd=0.0))
            continue
        near = N[(N.arm_utc - r.arm).abs() <= pd.Timedelta(seconds=10)]
        live = near.iloc[0] if len(near) else None
        if live is not None:
            buy, sell, src = live.buy_stop, live.sell_stop, "live log"
        else:
            prev = m.loc[:r.arm.floor("min") - pd.Timedelta(minutes=1)].iloc[-1]
            buy, sell, src = prev.close + prev.sp + OFFSET, prev.close - OFFSET, "previous minute close"
        fts, side, sure_fill = fill_side(m, r.arm, r.arm + pd.Timedelta(seconds=WINDOW), buy, sell)
        if live is not None and not sure_fill:
            # same orders at the same prices as the live bot: when the minute bars cannot place the touch inside the
            # 120-s window, the live log says whether they filled
            side = live.side if live.n_fills else ""
            fts = (live.fill_utc - pd.Timedelta(seconds=3)).floor("min") if live.n_fills else None
            src += " (fill as live)"
        if side == "":
            out.append(dict(base, stops_from=src, buy_stop=buy, sell_stop=sell, result="no fill", usd=0.0, sure=True))
            open_until = r.arm + pd.Timedelta(seconds=WINDOW)
            continue
        if side == "both":
            out.append(dict(base, stops_from=src, buy_stop=buy, sell_stop=sell, result="both stops in one minute",
                            usd=np.nan, sure=False))
            open_until = r.arm + pd.Timedelta(seconds=WINDOW)
            continue
        fill = buy if side == "BUY" else sell
        sl, tp = (fill - SL, fill + TP) if side == "BUY" else (fill + SL, fill - TP)
        ets, why, sure_exit = exit_from(m, side, fts, sl, tp)
        usd = {"take profit": TP, "stop loss": -SL}.get(why, np.nan) * LOT
        out.append(dict(base, stops_from=src, buy_stop=buy, sell_stop=sell, side=side, fill=fill, fill_minute=fts,
                        exit_minute=ets, result=why, usd=usd,
                        sure=bool(sure_exit and (sure_fill or "fill as live" in src))))
        open_until = ets + pd.Timedelta(minutes=1) if ets is not None else pd.Timestamp("2100-01-01")
    B = pd.DataFrame(out)
    B.to_csv(OUT / "nasdaq_nov9_m1_backtest.csv", index=False)
    print(B.drop(columns=["text"]).to_string(index=False))
    print("backtest USTECm Nov 9 from the M1 export:", round(B.usd.sum(), 2), "USD")


if __name__ == "__main__":
    main()
