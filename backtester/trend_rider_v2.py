"""Trend Rider v2 - judge the trend on a zoomed-out chart, enter on M1.

Why: v1 measured "trending vs consolidating" with ADX/Choppiness on the last
14 one-minute candles.  Every pullback inside a clean multi-hour trend lowers
M1 ADX and raises choppiness, so v1 switched itself off exactly at the
pullbacks that are the best entries (see results/chart_review/).

v2 trend regime, computed on COMPLETED higher-timeframe bars (default M5) and
carried onto the M1 chart without look-ahead:
    up   : HTF EMA(fast) > EMA(slow), EMA(slow) rising over `slope_bars`,
           HTF ADX > adx_min, and the move over the last `er_bars` HTF bars
           is clean - Kaufman efficiency ratio > er_min
    down : mirror image
Hysteresis: once a trend is on it stays on while HTF EMA(fast) stays beyond
EMA(slow) and HTF bars close beyond EMA(slow) - ordinary pullbacks no longer
switch it off; a close through the HTF EMA(slow) ends it.
The M1 chart must agree at entry: EMA20 > EMA50 > EMA200 and price above
EMA200 (mirror for shorts).

Entry on M1 (same idea as v1): the previous M1 candle dipped to EMA20 (or
within `touch_atr` x ATR of it) and the current candle closes back above
EMA20 and above the previous high.  Bracket, break-even, minimum stop in
price and the fill model are shared with trend_rider.py.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class Params:
    htf: str = "5min"
    htf_fast: int = 20
    htf_slow: int = 50
    slope_bars: int = 3
    adx_period: int = 14
    adx_min: float = 20.0
    er_bars: int = 12
    er_min: float = 0.30
    m1_ema: int = 20
    touch_atr: float = 0.2
    atr_period: int = 14
    swing_bars: int = 15
    min_stop_atr: float = 1.0
    max_stop_atr: float = 6.0
    min_stop_price: float = 0.0
    # bracket (read by trend_rider.backtest)
    rr: float = 3.0
    be_trigger: float = 1.0
    be_buffer: float = 0.1


def efficiency_ratio(c: pd.Series, n: int) -> pd.Series:
    return (c - c.shift(n)).abs() / c.diff().abs().rolling(n).sum()


def htf_regime(df: pd.DataFrame, p: Params) -> pd.Series:
    """+1 / -1 / 0 per M1 bar, from completed HTF bars only."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    h = df[["open", "high", "low", "close"]].resample(p.htf).agg(agg).dropna()
    f, s = ind.ema(h.close, p.htf_fast), ind.ema(h.close, p.htf_slow)
    _, _, adx = ind.adx(h, p.adx_period)
    er = efficiency_ratio(h.close, p.er_bars)
    clean = (adx > p.adx_min) & (er > p.er_min)
    start_up = (f > s) & (f > f.shift(p.slope_bars)) & (h.close > f) & clean
    start_dn = (f < s) & (f < f.shift(p.slope_bars)) & (h.close < f) & clean
    # hold through pullbacks while the HTF structure is intact
    hold_up = ((f > s) & (h.close > s)).to_numpy()
    hold_dn = ((f < s) & (h.close < s)).to_numpy()

    reg = np.zeros(len(h), np.int64)
    su, sd = start_up.to_numpy(), start_dn.to_numpy()
    for i in range(len(h)):
        prev = reg[i - 1] if i else 0
        if su[i]:
            reg[i] = 1
        elif sd[i]:
            reg[i] = -1
        elif prev == 1 and hold_up[i]:
            reg[i] = 1
        elif prev == -1 and hold_dn[i]:
            reg[i] = -1
    reg = pd.Series(reg, h.index)
    reg[s.isna() | adx.isna()] = 0
    # An HTF bar labelled t is complete at t + period; it can be used from the
    # M1 bar that closes at that instant (label t + period - 1 minute).
    step = pd.Timedelta(p.htf) - pd.Timedelta("1min")
    reg.index = reg.index + step
    return reg.reindex(df.index, method="ffill").fillna(0).astype(int)


def signals(df: pd.DataFrame, p: Params) -> pd.DataFrame:
    c, h, l = df["close"], df["high"], df["low"]
    e = ind.ema(c, p.m1_ema)
    a = ind.atr(df, p.atr_period)
    reg = htf_regime(df, p)

    tol = p.touch_atr * a.shift()
    pb_long = (l.shift() <= e.shift() + tol) & (c > e) & (c > h.shift())
    pb_short = (h.shift() >= e.shift() - tol) & (c < e) & (c < l.shift())

    floor = np.maximum(p.min_stop_atr * a, p.min_stop_price)
    cap = np.maximum(p.max_stop_atr * a, p.min_stop_price)
    long_dist = (c - l.rolling(p.swing_bars).min()).clip(lower=floor)
    short_dist = (h.rolling(p.swing_bars).max() - c).clip(lower=floor)

    # the M1 chart must agree: EMAs stacked and price on the right side of EMA200
    m50, m200 = ind.ema(c, 50), ind.ema(c, 200)
    m1_up = (e > m50) & (m50 > m200) & (c > m200)
    m1_dn = (e < m50) & (m50 < m200) & (c < m200)

    long_ = (reg == 1) & m1_up & pb_long & (long_dist <= cap)
    short_ = (reg == -1) & m1_dn & pb_short & (short_dist <= cap)
    sig = np.where(long_, 1, np.where(short_, -1, 0))
    dist = np.where(sig == 1, long_dist, np.where(sig == -1, short_dist, 0.0))
    out = pd.DataFrame({"signal": sig, "dist": np.nan_to_num(dist), "trend": reg}, index=df.index)
    out.loc[a.isna(), ["signal", "dist"]] = 0
    return out
